"""真实迁移与多连接竞争；仅显式 TEST_DATABASE_URL，始终在新建的临时库执行。"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import shutil
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from wellspring.db import get_db
from wellspring.main import app
from wellspring.models import Audit, Case, Organization, User
from wellspring.security import password_hash


@pytest.fixture(scope="module")
def pg_database():
    address = os.environ.get("TEST_DATABASE_URL")
    if not address:
        pytest.skip("需要显式指定隔离 PostgreSQL 测试服务器 TEST_DATABASE_URL")
    admin_url = make_url(address)
    if admin_url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL 必须为 PostgreSQL")
    name = "wellspring_test_" + uuid4().hex
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    engine = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        url = admin_url.set(database=name)
        environment = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
        backend = Path(__file__).resolve().parents[1]
        for arguments in (["upgrade", "0016"], ["upgrade", "head"], ["check"]):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *arguments], cwd=backend,
                env=environment, capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            assert result.returncode == 0, result.stderr
        engine = create_engine(url, pool_pre_ping=True)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def pg_context(pg_database):
    from wellspring.http_limits import login_limiter
    login_limiter.clear()
    factory = sessionmaker(pg_database, expire_on_commit=False)
    prefix = uuid4().hex[:10]
    with factory() as db:
        org = Organization(name=prefix)
        other = Organization(name=prefix + "-other")
        db.add_all([org, other])
        db.flush()
        encoded = password_hash("synthetic-test-password")
        users = [User(username=f"{prefix}-{name}", org_id=org.id, password_hash=encoded)
                 for name in ("alice", "receiver", "reviewer")]
        outsider = User(username=prefix + "-outsider", org_id=other.id, password_hash=encoded)
        db.add_all([*users, outsider])
        db.commit()
        identities = {user.username.split("-", 1)[1]: user.id for user in [*users, outsider]}

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            auth = {}
            for name in identities:
                response = client.post("/api/login", json={
                    "username": f"{prefix}-{name}", "password": "synthetic-test-password",
                })
                assert response.status_code == 200
                auth[name] = {"Authorization": "Bearer " + response.json()["token"]}
            yield client, factory, auth, identities
    finally:
        app.dependency_overrides.pop(get_db, None)


def command(client, path, auth, body, key=None):
    return client.post(path, headers={**auth, "Idempotency-Key": key or str(uuid4())}, json=body)


def race(first, second):
    barrier = Barrier(2, timeout=15)
    def invoke(callback):
        barrier.wait()
        return callback()
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(invoke, callback) for callback in (first, second)]
        return [future.result(timeout=30) for future in pending]




def test_same_idempotency_key_creates_one_case(pg_context):
    client, factory, auth, identities = pg_context
    key, number = str(uuid4()), uuid4().hex
    body = {"number": number, "title": "并发虚构案件"}
    call = lambda: command(client, "/api/cases", auth["alice"], body, key)
    replies = race(call, call)
    assert [response.status_code for response in replies] == [201, 201]
    assert replies[0].json() == replies[1].json()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Case).where(Case.number == number)) == 1
        assert db.scalar(select(func.count()).select_from(Audit).where(
            Audit.actor_id == identities["alice"], Audit.action == "CASE_CREATE")) == 1








def test_review_race_records_one_terminal_decision(pg_context):
    client, factory, auth, identities = pg_context
    clue = command(client, "/api/intelligence/clues", auth["alice"], {
        "title": "虚构线索", "summary": "并发复核测试", "source": "合成",
    })
    assert clue.status_code == 201
    clue_id = clue.json()["id"]
    review = command(client, f"/api/intelligence/clues/{clue_id}/review", auth["alice"],
                     {"version": 1, "note": "人工核验测试"})
    assert review.status_code == 200
    task = command(client, f"/api/intelligence/clues/{clue_id}/tasks", auth["alice"], {
        "clue_version": review.json()["version"], "objective": "测试", "assignee_id": identities["alice"],
    })
    assert task.status_code == 201
    path = f"/api/intelligence/tasks/{task.json()['id']}/transition"
    submitted = command(client, path, auth["alice"], {
        "version": 1, "action": "SUBMIT", "note": "合成结果", "result": "NO_FINDING",
    })
    assert submitted.status_code == 200
    replies = race(*(lambda action=action: command(client, path, auth["reviewer"], {
        "version": 2, "action": action, "note": "并发复核",
    }) for action in ("CLOSE", "RETURN")))
    assert sorted(response.status_code for response in replies) == [200, 409]


def test_runtime_role_can_append_but_cannot_rewrite_history(pg_database):
    import importlib.util
    from sqlalchemy.exc import DBAPIError
    path = Path(__file__).resolve().parents[2] / "deploy" / "offline" / "permissions.py"
    spec = importlib.util.spec_from_file_location("deployment_permissions", path)
    permissions = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(permissions)
    role = "test_runtime_" + uuid4().hex
    try:
        with pg_database.begin() as connection:
            connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS'))
            permissions.apply_runtime_permissions(connection, role)
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            assert connection.scalar(text("SELECT version_num FROM alembic_version"))
            for table in permissions.APPEND_ONLY_TABLES:
                assert connection.scalar(text("SELECT has_table_privilege(current_user, :table, 'INSERT')"), {"table": table})
        for table in permissions.APPEND_ONLY_TABLES:
            for verb in ("UPDATE", "DELETE"):
                with pytest.raises(DBAPIError):
                    with pg_database.begin() as connection:
                        connection.execute(text(f'SET LOCAL ROLE "{role}"'))
                        statement = f'UPDATE "{table}" SET id=id WHERE false' if verb == "UPDATE" else f'DELETE FROM "{table}" WHERE false'
                        connection.execute(text(statement))
        with pg_database.begin() as connection:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            connection.execute(text("DELETE FROM sessions WHERE false"))
            connection.execute(text("UPDATE cases SET status=status WHERE false"))
            connection.execute(text("UPDATE intake_case_links SET status=status, version=version WHERE false"))
        with pytest.raises(DBAPIError):
            with pg_database.begin() as connection:
                connection.execute(text(f'SET LOCAL ROLE "{role}"'))
                connection.execute(text("UPDATE intake_case_links SET source_snapshot=source_snapshot WHERE false"))
    finally:
        with pg_database.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{role}"'))
            connection.execute(text(f'DROP ROLE "{role}"'))


def test_database_dump_restore_preserves_all_rows(pg_database, tmp_path):
    """真实 pg_dump/pg_restore；二进制目录只能显式传入或取 PATH，不操作现有库。"""
    directory = os.environ.get("POSTGRES_BIN")
    suffix = ".exe" if sys.platform == "win32" else ""
    dump = str(Path(directory) / ("pg_dump" + suffix)) if directory else shutil.which("pg_dump")
    restore = str(Path(directory) / ("pg_restore" + suffix)) if directory else shutil.which("pg_restore")
    if not dump or not restore:
        pytest.skip("未安装匹配版本的 PostgreSQL 备份客户端")
    source_url = pg_database.url
    admin = create_engine(source_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    name = "wellspring_restore_" + uuid4().hex
    environment = {**os.environ, "PGPASSWORD": source_url.password or ""}
    arguments = ["-h", source_url.host, "-p", str(source_url.port or 5432), "-U", source_url.username]
    archive = tmp_path / "synthetic.dump"
    restored = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        subprocess.run([dump, *arguments, "-Fc", "-f", str(archive), source_url.database],
                       env=environment, check=True, capture_output=True, timeout=60)
        subprocess.run([restore, *arguments, "--exit-on-error", "--no-owner", "--no-acl", "-d", name, str(archive)],
                       env=environment, check=True, capture_output=True, timeout=60)
        restored = create_engine(source_url.set(database=name))
        def snapshot(engine):
            with engine.connect() as connection:
                tables = connection.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).all()
                return {table: connection.scalars(text(
                    f'SELECT row_to_json(record)::text FROM "{table}" record ORDER BY row_to_json(record)::text')).all()
                        for table in tables}
        assert snapshot(pg_database) == snapshot(restored)
    finally:
        if restored is not None:
            restored.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def predecessor_database(pg_database):
    address=pg_database.url.set(database='postgres')
    owner=create_engine(address,isolation_level='AUTOCOMMIT')
    name='wellspring_predecessor_'+uuid4().hex
    with owner.connect() as connection:connection.execute(text(f'CREATE DATABASE "{name}"'))
    url=address.set(database=name);engine=create_engine(url)
    from alembic import command
    from wellspring import startup_migrations as migration
    config=migration.configuration()
    try:
        with engine.begin() as connection:
            config.attributes['connection']=connection;command.upgrade(config,'0017')
        config.attributes.pop('connection',None);engine.dispose()
        yield engine
    finally:
        engine.dispose()
        with owner.connect() as connection:connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        owner.dispose()


def test_startup_upgrade_uses_real_backup_and_shared_migration_connection(predecessor_database,tmp_path):
    from wellspring import startup_migrations as migration
    engine=predecessor_database;snapshots=tmp_path/'snapshots'
    assert migration.upgrade(engine.url,automatic=False,backup_dir=snapshots)
    archive=next(snapshots.glob('*.dump'))
    import hashlib,json
    record=json.loads(archive.with_suffix('.dump.json').read_text())
    assert record['from']==['0017'] and record['sha256']==hashlib.sha256(archive.read_bytes()).hexdigest()
    with engine.connect() as connection:assert connection.scalar(text('SELECT version_num FROM alembic_version'))==record['to']


def test_postgres_startup_lock_timeout_and_unsafe_migration_refusal(predecessor_database,tmp_path):
    from wellspring import startup_migrations as migration
    engine=predecessor_database
    with engine.connect() as connection:
        with migration.postgres_lock(connection):
            with pytest.raises(migration.MigrationRefused,match='等待超时'):
                migration.upgrade(engine.url,automatic=False,backup_dir=tmp_path,lock_timeout=0)
    with pytest.raises(migration.MigrationRefused,match='未批准'):
        migration.upgrade(engine.url,backup_dir=tmp_path)


def test_wastewater_numeric_and_review_race(pg_context):
    client, factory, auth, identities = pg_context
    root = "/api/wastewater"
    point = command(client, root + "/sites", auth["alice"], {"code": uuid4().hex, "name": "合成点位", "district": "合成区域"})
    assert point.status_code == 201
    bottle = command(client, root + "/samples", auth["alice"], {"site_id": point.json()["id"], "code": uuid4().hex,
        "sampled_at": "2026-11-10T08:00:00+08:00", "sampling_method": "COMPOSITE", "collector": "合成采样员", "quality": "VALID"})
    assert bottle.status_code == 201
    result = command(client, root + "/results", auth["alice"], {"sample_id": bottle.json()["id"], "analyte": "合成指标", "detection": "QUANTIFIED",
        "concentration": "99999999999999.999999", "laboratory": "合成实验室", "analysis_method": "合成方法", "report_number": uuid4().hex})
    assert result.status_code == 201
    identity = result.json()["id"]
    replies = race(*(lambda action=action: command(client, f"{root}/results/{identity}/review", auth["reviewer"], {"version": 1, "action": action, "note": "并发核对"}) for action in ("CONFIRM", "RETURN")))
    assert sorted(reply.status_code for reply in replies) == [200, 409]
    from wellspring.wastewater_models import WastewaterResult, WastewaterResultEvent
    with factory() as db:
        assert db.get(WastewaterResult, identity).concentration == Decimal("99999999999999.999999")
        assert db.scalar(select(func.count()).select_from(WastewaterResultEvent).where(WastewaterResultEvent.result_id == identity)) == 2


@pytest.mark.parametrize("same_key", [True, False])
def test_intake_conversion_race_creates_only_one_case(pg_context, same_key):
    client, factory, auth, identities = pg_context
    number = "INTAKE-" + uuid4().hex
    assert command(client, "/api/case-information/import", auth["alice"], {"rows": [{"接警编号": number, "报警内容": "合成来源"}]}).status_code == 201
    source = client.post("/api/case-information/search", headers=auth["alice"], json={"keyword": number}).json()["items"][0]
    route = f"/api/case-information/{source['id']}/case-link"
    case_number = uuid4().hex
    body = {"source_version": 1, "mode": "NEW", "number": case_number, "title": "并发转办案件", "basis": "并发合成测试"}
    shared = str(uuid4()) if same_key else None
    replies = race(*(lambda: command(client, route, auth["alice"], body, shared) for _ in range(2)))
    assert sorted(reply.status_code for reply in replies) == ([201, 201] if same_key else [201, 409])
    from wellspring.intake_models import IntakeCaseLink
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Case).where(Case.number == case_number)) == 1
        assert db.scalar(select(func.count()).select_from(IntakeCaseLink).where(IntakeCaseLink.intake_id == source["id"])) == 1
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.actor_id == identities["alice"], Audit.action == "INTAKE_CASE_LINK")) == 1


def test_concurrent_admin_disable_preserves_one_superadministrator(pg_context):
    client,factory,auth,identities=pg_context
    with factory() as db:
        for name in ('alice','reviewer'):
            db.get(User,identities[name]).is_admin=True
        db.commit()
        org=db.get(User,identities['alice']).org_id
    replies=race(*(lambda name=name:command(client,f"/api/system/users/{identities[name]}/update",auth[name],
        {'version':1,'org_id':org,'role_id':None,'is_admin':True,'active':False}) for name in ('alice','reviewer')))
    assert sorted(reply.status_code for reply in replies)==[200,409]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.org_id==org,User.is_admin.is_(True),User.active.is_(True)))==1
