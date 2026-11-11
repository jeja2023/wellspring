"""Controlled local-development upgrades; the API process never runs DDL."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from . import models  # Register current metadata before migration checks.

BACKEND = Path(__file__).resolve().parents[1]
LOCK_KEY = 6285783391490618963


class MigrationRefused(RuntimeError):
    pass


@contextmanager
def sqlite_lock(database, timeout=30):
    """OS releases the lock on crash; a persistent empty lock file is harmless."""
    path = Path(str(database) + ".migration.lock")
    with open(path, "a+b") as stream:
        if not path.stat().st_size:
            stream.write(b"0"); stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise MigrationRefused("另一个迁移正在执行，等待超时；本次不启动服务") from None
                time.sleep(0.1)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def postgres_lock(connection, timeout=30):
    deadline = time.monotonic() + timeout
    while not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}):
        connection.rollback()
        if time.monotonic() >= deadline:
            raise MigrationRefused("另一个迁移正在执行，等待超时；本次不启动服务")
        time.sleep(0.1)
    connection.commit()
    try:
        yield
    finally:
        connection.rollback()
        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
        connection.commit()


def configuration():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return config


def pending_revisions(connection, config):
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    current = MigrationContext.configure(connection).get_current_heads()
    if len(heads) != 1 or len(current) > 1:
        raise MigrationRefused("迁移存在多个分支，请先人工检查，不能自动合并")
    if not current and inspect(connection).get_table_names():
        raise MigrationRefused("数据库已有表但没有有效迁移版本；禁止自动接管或标记版本")
    try:
        revisions = list(reversed(list(scripts.iterate_revisions(heads[0], current or "base"))))
    except Exception:
        raise MigrationRefused("数据库版本未知、领先或迁移链不完整；请使用匹配的程序版本") from None
    return current, heads[0], revisions


def private_file(path, data):
    with open(path, "xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def pg_dump_binary(connection):
    major = int(connection.scalar(text("SHOW server_version_num"))) // 10000
    candidates = []
    for variable in ("WELLSPRING_PG_BIN", "POSTGRES_BIN"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / ("pg_dump.exe" if os.name == "nt" else "pg_dump"))
    if shutil.which("pg_dump"):
        candidates.append(Path(shutil.which("pg_dump")))
    if os.name == "nt":
        candidates.append(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PostgreSQL" / str(major) / "bin/pg_dump.exe")
    for path in candidates:
        if path.is_file():
            result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10)
            match = re.search(r"PostgreSQL\) (\d+)\.", result.stdout)
            if result.returncode == 0 and match and int(match[1]) == major:
                return path
    raise MigrationRefused(f"未找到 PostgreSQL {major} 的 pg_dump；请安装匹配客户端或设置 WELLSPRING_PG_BIN")


def backup_database(connection, url, directory, current, target):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    suffix = ".sqlite3" if url.get_backend_name() == "sqlite" else ".dump"
    path = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex + suffix)
    temporary = path.with_suffix(suffix + ".partial")
    private_file(temporary, b"")
    try:
        if url.get_backend_name() == "sqlite":
            with closing(sqlite3.connect(Path(url.database).resolve().as_uri() + "?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(temporary)) as destination:
                    source.backup(destination)
                    # Old schema CHECK functions belong to its historical migration only.
                    if destination.execute("SELECT 1 FROM sqlite_master WHERE sql LIKE '%wellspring_decimal_valid%' LIMIT 1").fetchone():
                        ScriptDirectory.from_config(configuration()).get_revision('0017').module.register_historical_functions(destination)
                    if destination.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                        raise MigrationRefused("SQLite 备份完整性检查失败；本次不执行迁移")
        else:
            binary = pg_dump_binary(connection)
            allowed = {"sslmode", "sslrootcert", "sslcert", "sslkey", "sslcrl", "channel_binding", "gssencmode"}
            if set(url.query) - allowed:
                raise MigrationRefused("数据库 URL 包含不能安全映射到备份客户端的参数，请人工处理")
            env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
            env.update(PGHOST=url.host or "localhost", PGPORT=str(url.port or 5432), PGDATABASE=url.database or "",
                       PGUSER=url.username or "", PGPASSWORD=url.password or "", PGCONNECT_TIMEOUT="5")
            env.update({"PG" + key.upper(): str(value) for key, value in url.query.items()})
            subprocess.run([str(binary), "--no-password", "-Fc", "-f", str(temporary)], env=env,
                           check=True, capture_output=True, timeout=300)
        if not temporary.stat().st_size:
            raise MigrationRefused("备份文件为空；本次不执行迁移")
        digest = hashlib.sha256()
        with temporary.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        os.link(temporary, path)  # Atomic publication without overwriting existing backups.
        metadata = {"created_at": datetime.now(timezone.utc).isoformat(), "from": list(current), "to": target,
                    "file": path.name, "sha256": digest.hexdigest(), "database_kind": url.get_backend_name(),
                    "database": url.database, "host": url.host, "port": url.port}
        private_file(path.with_suffix(suffix + ".json"), json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"))
        print(f"迁移前备份已保存：{path}", flush=True)
        return path
    finally:
        temporary.unlink(missing_ok=True)


def upgrade(database_url, *, automatic=True, check_only=False, backup_dir=None, config=None, lock_timeout=30):
    url = make_url(database_url)
    backend = url.get_backend_name()
    if backend not in {"sqlite", "postgresql"} or (backend == "sqlite" and (not url.database or url.database == ":memory:" or url.query)):
        raise MigrationRefused("受控迁移仅支持磁盘 SQLite 和 PostgreSQL")
    if check_only and backend == "sqlite" and not Path(url.database).is_file():
        raise MigrationRefused("数据库不存在；本次只检查，不创建数据库或启动服务")
    config = config or configuration()
    backup_root = Path(backup_dir or BACKEND / "backups/startup")
    identity = json.dumps([url.host, url.port or 5432, url.database], ensure_ascii=False)
    marker = (Path(str(Path(url.database).resolve()) + ".migration.failed.json") if backend == "sqlite" else
              backup_root / ("migration-" + hashlib.sha256(identity.encode()).hexdigest() + ".failed.json"))
    options = {"connect_timeout": 5, "application_name": "wellspring-migration"} if backend == "postgresql" else {}
    engine = create_engine(url, poolclass=NullPool, connect_args=options, hide_parameters=True)
    try:
        # The SQLite file lock must be acquired before creating/opening the database.
        with sqlite_lock(Path(url.database).resolve(), lock_timeout) if backend == "sqlite" else engine.connect() as outer:
            connection = engine.connect() if backend == "sqlite" else outer
            try:
                with postgres_lock(connection, lock_timeout) if backend == "postgresql" else _no_lock():
                    if marker.exists() and (automatic or check_only):
                        raise MigrationRefused(f"上次迁移可能失败或中断；请停服并检查备份，人工处理后再执行 python migrate.py。标记：{marker}")
                    current, target, revisions = pending_revisions(connection, config)
                    if not revisions:
                        if not automatic and not check_only:
                            marker.unlink(missing_ok=True)
                        print(f"数据库已是最新版本 {target}，无须迁移。", flush=True)
                        return False
                    identifiers = ", ".join(revision.revision for revision in revisions)
                    if check_only:
                        raise MigrationRefused(f"存在待执行迁移 {identifiers}；本次只检查，不启动服务")
                    # Fresh empty databases have no historical data to transform.
                    unsafe = [revision.revision for revision in revisions if getattr(revision.module, "startup_safe", False) is not True]
                    if automatic and current and unsafe:
                        raise MigrationRefused(f"迁移 {', '.join(unsafe)} 未批准为启动时安全执行；请先停服后运行 python migrate.py")
                    if backend == "postgresql":
                        if automatic and connection.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend' AND application_name<>'wellspring-migration'")):
                            raise MigrationRefused("数据库仍有其他连接；请先停止旧服务并关闭数据库客户端")
                        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                        connection.execute(text("SET LOCAL statement_timeout = '10min'"))
                        tables = inspect(connection).get_table_names(schema="public")
                        if tables:
                            quoted = ", ".join('public.' + connection.dialect.identifier_preparer.quote(table) for table in tables)
                            connection.execute(text("LOCK TABLE " + quoted + " IN SHARE MODE"))
                    snapshot = backup_database(connection, url, backup_root, current, target) if current else None
                    # Persist BEFORE DDL, so a crash cannot silently retry against
                    # a partially altered SQLite schema on the next launch.
                    marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    if not marker.exists():
                        private_file(marker, json.dumps({"from": list(current), "to": target,
                            "backup": str(snapshot) if snapshot else None}, ensure_ascii=False).encode("utf-8"))
                    print(f"正在执行迁移：{identifiers}", flush=True)
                    config.attributes["connection"] = connection
                    command.upgrade(config, target)
                    if MigrationContext.configure(connection).get_current_heads() != (target,):
                        raise MigrationRefused("迁移后版本检查失败；本次不启动服务，请核对备份和数据库")
                    connection.commit()
                    marker.unlink()
                    print(f"迁移完成，数据库版本：{target}。", flush=True)
                    return True
            finally:
                if backend == "sqlite":
                    connection.close()
    finally:
        config.attributes.pop("connection", None)
        engine.dispose()


@contextmanager
def _no_lock():
    yield


def main():
    import argparse
    parser = argparse.ArgumentParser(description="本地开发受控迁移：备份成功后才升级，失败停止启动")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--manual", action="store_true", help="显式手动执行含数据转换的迁移，仍会先备份")
    mode.add_argument("--check-only", action="store_true", help="只核对版本，不升级")
    args = parser.parse_args()
    try:
        upgrade(os.getenv("DATABASE_URL", "sqlite:///./wellspring-dev.db"), automatic=not args.manual, check_only=args.check_only)
    except MigrationRefused as error:
        print(f"停止启动：{error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"迁移未完成（{type(error).__name__}），服务未启动。请检查数据库和迁移前备份；不要直接降级或重试覆盖。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
