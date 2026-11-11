from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import asyncio
import os
import subprocess
import sys

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from wellspring.main import expected_schema_heads
from wellspring.models import Audit, CaseInformation, InvestigationTask, Session, User
from test_workflow import context, auth, headers


def test_exact_sqlite_weight_boundary_and_numeric_order(context):
    client, factory = context
    actor = auth(client, "alice")
    case = client.post("/api/cases", headers=headers(actor), json={"number": "EXACT", "title": "test"}).json()
    maximum = "99999999999999.999999"
    items = []
    for weight in (maximum, "2", "10"):
        response = client.post("/api/evidence", headers=headers(actor), json={"case_id": case["id"], "label": weight, "weight": weight, "reason": "test"})
        assert response.status_code == 201
        items.append(response.json())
    page = client.get("/api/evidence?sort=balance&order=asc", headers=actor).json()
    assert [Decimal(row["balance"]) for row in page["items"]] == [Decimal(2), Decimal(10), Decimal(maximum)]
    response = client.post(f"/api/evidence/{items[0]['id']}/samples", headers=headers(actor), json={"source_version": 1, "label": "micro", "weight": "0.000001", "reason": "test"})
    assert response.status_code == 201
    page = client.get("/api/evidence", headers=actor).json()
    related = [row for row in page["items"] if row["id"] == items[0]["id"] or row["parent_id"] == items[0]["id"]]
    assert sum(Decimal(row["balance"]) for row in related) == Decimal(maximum)
    with factory() as db:
        assert db.execute(text("SELECT typeof(balance) FROM evidence LIMIT 1")).scalar() == "text"
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE evidence SET balance = '-1.000000' WHERE id = :id"), {"id": items[0]["id"]})


def test_created_and_reloaded_timestamps_always_include_utc(context):
    client, _ = context
    actor = auth(client, "alice")
    created = client.post("/api/cases", headers=headers(actor), json={"number": "UTC", "title": "test"}).json()
    reloaded = client.get("/api/cases", headers=actor).json()["items"][0]
    assert datetime.fromisoformat(created["created_at"]).utcoffset() == timedelta(0)
    assert datetime.fromisoformat(reloaded["created_at"]).utcoffset() == timedelta(0)
    assert created["created_at"] == reloaded["created_at"]


def test_stored_filter_values_remain_searchable_and_summary_is_optional(context):
    client, factory = context
    actor = auth(client, "alice")
    value = "长" * 201
    assert client.post("/api/case-information/import", headers=headers(actor), json={"rows": [{"number": "LONG", "alarm_type": value, "result": value}]}).status_code == 201
    found = client.post("/api/case-information/search", headers=actor, json={"alarm_type": value, "result": value})
    assert found.status_code == 200 and found.json()["total"] == 1
    assert found.json()["options"]["types"] == [value]
    page = client.post("/api/case-information/search", headers=actor, json={"include_summary": False}).json()
    assert page["total"] == 1 and "statistics" not in page and "options" not in page
    queries = []

    def record_query(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    engine = factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", record_query)
    try:
        client.post("/api/case-information/search", headers=actor, json={"include_summary": True})
        with_summary = len(queries)
        queries.clear()
        client.post("/api/case-information/search", headers=actor, json={"include_summary": False})
        assert with_summary - len(queries) == 4
    finally:
        event.remove(engine, "before_cursor_execute", record_query)


def test_export_stops_at_character_budget_without_recording_success(context):
    from wellspring.case_information_schema import CaseInformationFields
    client, factory = context
    actor = auth(client, "alice")
    large_fields = {name: "x" * 10000 for name in CaseInformationFields.model_fields if name != "number"}
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        db.add_all(CaseInformation(number=f"LARGE-{number}", org_id=user.org_id, created_by=user.id, **large_fields) for number in range(12))
        db.commit()
    response = client.post("/api/case-information/export", headers=actor, json={})
    assert response.status_code == 422 and response.json()["code"] == "EXPORT_TOO_LARGE"
    with factory() as db:
        assert db.scalar(select(Audit.id).where(Audit.action == "CASE_INFORMATION_EXPORT")) is None
    response = client.post("/api/case-information/export", headers=actor, json={"keyword": "LARGE-0"})
    assert response.status_code == 200 and len(response.json()["items"]) == 1


def test_case_list_summary_fetches_full_authorized_detail_before_editing(context):
    client, factory = context
    actor, other = auth(client, "alice"), auth(client, "bob")
    number = "N" * 80
    original = {"number": number, "alarm_content": "正文" * 300, "caller": "完整报警人", "note": "必须保留的备注", "tags": "完整标签"}
    assert client.post("/api/case-information/import", headers=headers(actor), json={"rows": [original]}).status_code == 201
    queries = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    engine = factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.post("/api/case-information/search", headers=actor, json={"summary_only": True, "include_summary": False})
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    item = response.json()["items"][0]
    assert item["is_summary"] is True and item["接警编号"] == number
    assert item["报警内容"] == original["alarm_content"][:200]
    assert "报警人" not in item and "备注" not in item and "标签" not in item
    # Auth uses session/user/organization/role SELECTs; data uses count/projected page, with no
    # per-row deferred field access or full text fetch in the projected query.
    assert len(queries) == 6
    assert "substr(" in queries[-1].lower() and "case_information.caller" not in queries[-1]
    path = f"/api/case-information/{item['id']}/detail"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=other).status_code == 404
    detail = client.get(path, headers=actor).json()
    assert detail["is_summary"] is False and detail["报警内容"] == original["alarm_content"]
    assert detail["备注"] == original["note"] and detail["报警人"] == original["caller"]
    exported = client.post("/api/case-information/export", headers=actor, json={}).json()["items"][0]
    assert exported["报警内容"] == original["alarm_content"] and exported["备注"] == original["note"]
    fields = {key: value for key, value in detail.items() if key not in ("id", "version", "is_summary", "can_link_case", "case_link")}
    fields["接警类型"] = "修改类型"
    assert client.post(f"/api/case-information/{item['id']}/update", headers=headers(actor), json={"version": detail["version"], "fields": fields}).status_code == 200
    after = client.get(path, headers=actor).json()
    assert after["报警内容"] == original["alarm_content"] and after["备注"] == original["note"]
    assert after["报警人"] == original["caller"] and after["标签"] == original["tags"]


@pytest.mark.parametrize("username,password", [("x" * 81, "x" * 12), ("valid", "x" * 257)])
def test_bootstrap_rejects_credentials_that_login_cannot_accept(context, monkeypatch, username, password):
    from wellspring import bootstrap
    _, factory = context
    monkeypatch.setattr(bootstrap, "SessionLocal", factory)
    answers = iter([username, "test"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(bootstrap.getpass, "getpass", lambda _: password)
    with pytest.raises(SystemExit):
        bootstrap.main()
    with factory() as db:
        assert db.scalar(select(User.id).where(User.username == username)) is None


def test_case_information_replay_rechecks_revoked_cross_org_permission(context):
    client, factory = context
    actor, other = auth(client, "alice"), auth(client, "bob")
    client.post("/api/case-information/import", headers=headers(other), json={"rows": [{"number": "B"}]})
    item = client.post("/api/case-information/search", headers=other, json={}).json()["items"][0]
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "alice")); user.is_admin = True; db.commit()
    key = headers(actor)
    body = {"version": 1, "fields": {"number": "B", "note": "test"}}
    url = f"/api/case-information/{item['id']}/update"
    assert client.post(url, headers=key, json=body).status_code == 200
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "alice")); user.is_admin = False; db.commit()
    assert client.post(url, headers=key, json=body).status_code == 404


def test_review_refuses_missing_submitter(context):
    client, factory = context
    actor = auth(client, "alice")
    clue = client.post("/api/intelligence/clues", headers=headers(actor), json={"title": "test", "summary": "test", "source": "test"}).json()
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        task = InvestigationTask(org_id=user.org_id, clue_id=clue["id"], objective="test", assignee_id=user.id, status="PENDING_REVIEW", last_submitter_id=None)
        db.add(task); db.commit(); task_id = task.id
    response = client.post(f"/api/intelligence/tasks/{task_id}/transition", headers=headers(actor), json={"version": 1, "action": "CLOSE", "note": "test"})
    assert response.status_code == 403


def test_readiness_checks_database_schema(context):
    client, factory = context
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/ready").status_code == 503
    with factory() as db:
        db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        db.execute(text("INSERT INTO alembic_version VALUES ('obsolete')")); db.commit()
    assert client.get("/api/ready").status_code == 503
    with factory() as db:
        db.execute(text("UPDATE alembic_version SET version_num = :version"), {"version": next(iter(expected_schema_heads()))}); db.commit()
    assert client.get("/api/ready").status_code == 200


def test_login_is_throttled_and_cleans_expired_sessions(context, monkeypatch):
    client, factory = context
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        db.add(Session(token_hash="expired", user_id=user.id, expires_at=datetime.now(timezone.utc) - timedelta(days=1))); db.commit()
    auth(client, "alice")
    with factory() as db:
        assert db.get(Session, "expired") is None
    monkeypatch.setenv("WELLSPRING_LOGIN_ACCOUNT_LIMIT", "2")
    for _ in range(2):
        assert client.post("/api/login", json={"username": "missing", "password": "bad"}).status_code == 401
    limited = client.post("/api/login", json={"username": "missing", "password": "bad"})
    assert limited.status_code == 429 and limited.headers["Retry-After"] == "60"


def test_request_budget_bounds_both_declared_and_streamed_bodies(context, monkeypatch):
    client, _ = context
    monkeypatch.setenv("WELLSPRING_MAX_REQUEST_BYTES", "32")
    response = client.post("/api/login", content="x" * 33)
    assert response.status_code == 413 and response.json()["request_id"] == response.headers["X-Request-ID"]
    response = client.post("/api/login", content=iter([b"x" * 20, b"x" * 20]))
    assert response.status_code == 413


def test_request_body_timeout_stops_slow_clients(monkeypatch):
    from wellspring.http_limits import RequestBudgetMiddleware
    monkeypatch.setenv("WELLSPRING_REQUEST_BODY_TIMEOUT", "0.01")
    messages = []

    async def application(*_args):
        pytest.fail("a timed-out body must not reach the application")

    async def receive():
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": True}

    async def send(message):
        messages.append(message)

    asyncio.run(RequestBudgetMiddleware(application)({"type": "http", "method": "POST", "headers": []}, receive, send))
    assert messages[0]["status"] == 408


def test_sqlite_weight_migration_preserves_values_and_schema(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "migration.db"
    environment = {**os.environ, "DATABASE_URL": "sqlite:///" + database.as_posix()}

    def migrate(*arguments):
        result = subprocess.run([sys.executable, "-m", "alembic", *arguments], cwd=backend, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert result.returncode == 0, result.stderr + result.stdout

    migrate("upgrade", "0016")
    import sqlite3
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO organizations (id,name) VALUES ('org', 'test')")
        db.execute("INSERT INTO cases VALUES ('case', 'org', 'N', 'test', 'DRAFT', '2020-01-01')")
        db.execute("INSERT INTO evidence VALUES ('e', 'org', 'case', NULL, 'test', 10.123456, 1, '2020-01-01')")
    migrate("upgrade", "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT balance, typeof(balance) FROM evidence").fetchone() == ("10.123456", "text")
    migrate("check")
