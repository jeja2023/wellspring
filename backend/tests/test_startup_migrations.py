"""Upgrade real disposable databases, including backup and startup refusal paths."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sqlite3
import sys

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text

from wellspring import startup_migrations as migrations


@pytest.fixture
def history(tmp_path):
    scripts = tmp_path / "migrations"
    (scripts / "versions").mkdir(parents=True)
    (scripts / "env.py").write_text('''
from alembic import context
from sqlalchemy import create_engine
config = context.config
def run(connection):
    context.configure(connection=connection)
    with context.begin_transaction(): context.run_migrations()
connection = config.attributes.get('connection')
if connection is not None:
    run(connection)
else:
    with create_engine(config.get_main_option('sqlalchemy.url')).connect() as connection: run(connection)
''', encoding="utf-8")
    def revision(name, previous, safe, body):
        (scripts / "versions" / (name + ".py")).write_text(
            f"from alembic import op\nimport sqlalchemy as sa\nrevision={name!r}\ndown_revision={previous!r}\nstartup_safe={safe!r}\ndef upgrade():\n    {body}\ndef downgrade():\n    pass\n", encoding="utf-8")
    revision("a", None, False, "op.create_table('demo', sa.Column('id', sa.Integer, primary_key=True), sa.Column('value', sa.Text))")
    revision("b", "a", True, "op.add_column('demo', sa.Column('extra', sa.Text))")
    database = tmp_path / "synthetic.db"
    config = Config()
    config.set_main_option("script_location", str(scripts))
    config.set_main_option("sqlalchemy.url", "sqlite:///" + database.as_posix())
    command.upgrade(config, "a")
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO demo VALUES (1, 'synthetic-private-value')")
    return config, database, tmp_path / "backups", revision


def test_approved_upgrade_creates_restorable_snapshot_and_repeated_start_is_noop(history):
    config, database, backups, _ = history
    url = "sqlite:///" + database.as_posix()
    assert migrations.upgrade(url, config=config, backup_dir=backups)
    snapshot = next(backups.glob("*.sqlite3"))
    metadata = json.loads(snapshot.with_suffix(".sqlite3.json").read_text())
    assert metadata["from"] == ["a"] and metadata["to"] == "b"
    assert metadata["sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    with sqlite3.connect(snapshot) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("a",)
        assert connection.execute("SELECT * FROM demo").fetchone() == (1, "synthetic-private-value")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("b",)
        assert connection.execute("SELECT extra FROM demo").fetchone() == (None,)
    assert migrations.upgrade(url, config=config, backup_dir=backups) is False
    assert len(list(backups.glob("*.sqlite3"))) == 1


def test_unapproved_data_migration_requires_explicit_manual_command(history):
    config, database, backups, revision = history
    revision("c", "b", False, "op.execute(\"UPDATE demo SET value='converted'\")")
    url = "sqlite:///" + database.as_posix()
    with pytest.raises(migrations.MigrationRefused, match="未批准"):
        migrations.upgrade(url, config=config, backup_dir=backups)
    assert not backups.exists()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM demo").fetchone()[0] == "synthetic-private-value"
    assert migrations.upgrade(url, automatic=False, config=config, backup_dir=backups)


def test_backup_failure_never_enters_upgrade(history, monkeypatch):
    config, database, backups, _ = history
    def fail(*_args):
        raise OSError("synthetic backup storage unavailable")
    monkeypatch.setattr(migrations, "backup_database", fail)
    monkeypatch.setattr(migrations.command, "upgrade", lambda *_: pytest.fail("no DDL before backup succeeds"))
    with pytest.raises(OSError):
        migrations.upgrade("sqlite:///" + database.as_posix(), config=config, backup_dir=backups)


def test_migration_failure_preserves_backup_and_releases_lock(history, monkeypatch):
    config, database, backups, _ = history
    def fail(*_args):
        raise RuntimeError("synthetic DDL failure")
    monkeypatch.setattr(migrations.command, "upgrade", fail)
    with pytest.raises(RuntimeError, match="synthetic DDL"):
        migrations.upgrade("sqlite:///" + database.as_posix(), config=config, backup_dir=backups)
    assert len(list(backups.glob("*.sqlite3"))) == 1
    with pytest.raises(migrations.MigrationRefused, match="上次迁移"):
        migrations.upgrade("sqlite:///" + database.as_posix(), config=config, backup_dir=backups)
    with migrations.sqlite_lock(database, timeout=0):
        pass


def test_check_only_and_unknown_schema_never_change_database(history):
    config, database, backups, _ = history
    url = "sqlite:///" + database.as_posix()
    with pytest.raises(migrations.MigrationRefused, match="只检查"):
        migrations.upgrade(url, config=config, backup_dir=backups, check_only=True)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE alembic_version SET version_num='future'")
    with pytest.raises(migrations.MigrationRefused, match="未知"):
        migrations.upgrade(url, config=config, backup_dir=backups)
    assert not backups.exists()


def test_nonempty_unversioned_database_is_not_adopted(tmp_path):
    database = tmp_path / "unversioned.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE existing (id INTEGER)")
    with pytest.raises(migrations.MigrationRefused, match="已有表"):
        migrations.upgrade("sqlite:///" + database.as_posix(), backup_dir=tmp_path / "backups")


def test_file_lock_prevents_concurrent_upgrade(history):
    _, database, _, _ = history
    with migrations.sqlite_lock(database):
        with pytest.raises(migrations.MigrationRefused, match="等待超时"):
            with migrations.sqlite_lock(database, timeout=0):
                pytest.fail("must not enter a second migration")


def test_first_install_runs_real_migration_chain_on_empty_database(tmp_path):
    database = tmp_path / "new.db"
    assert migrations.upgrade("sqlite:///" + database.as_posix(), backup_dir=tmp_path / "backups")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == tuple(migrations.ScriptDirectory.from_config(migrations.configuration()).get_heads())
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("arguments,expected", [([], []), (["--no-auto-migrate"], ["--check-only"])])
def test_launcher_does_not_start_services_when_migration_is_refused(tmp_path, monkeypatch, arguments, expected):
    path = Path(__file__).resolve().parents[2] / "start.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("startup_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    vite = tmp_path / "vite.js"
    vite.write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher, "VITE", vite)
    monkeypatch.setattr(launcher, "VENV_PYTHON", Path(sys.executable))
    monkeypatch.setattr(sys, "argv", ["start.py", *arguments])
    monkeypatch.setattr(launcher, "free_port", lambda _: True)
    monkeypatch.setattr(launcher.shutil, "which", lambda _: "node")
    monkeypatch.setattr(launcher, "database_environment", lambda _: {"DATABASE_URL": "sqlite:///unused.db"})
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return type("Result", (), {"returncode": 1})()
    monkeypatch.setattr(launcher.subprocess, "run", run)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("must not start API or Vite"))
    assert launcher.main() == 1
    assert calls[0][1:] == ["-m", "wellspring.startup_migrations", *expected]


def test_multiple_heads_require_manual_resolution(history):
    config, database, backups, revision = history
    revision("branch", "a", True, "pass")
    with pytest.raises(migrations.MigrationRefused, match="多个分支"):
        migrations.upgrade("sqlite:///" + database.as_posix(), config=config, backup_dir=backups)
    assert not backups.exists()


def test_check_only_missing_database_does_not_create_it(tmp_path):
    database = tmp_path / "missing.db"
    with pytest.raises(migrations.MigrationRefused, match="数据库不存在"):
        migrations.upgrade("sqlite:///" + database.as_posix(), check_only=True)
    assert not database.exists()


def test_generated_revision_defaults_to_manual_review(tmp_path):
    import shutil
    config = Config()
    scripts = tmp_path / "template"
    (scripts / "versions").mkdir(parents=True)
    shutil.copyfile(migrations.BACKEND / "migrations/script.py.mako", scripts / "script.py.mako")
    config.set_main_option("script_location", str(scripts))
    revision = command.revision(config, message="synthetic new migration")
    assert revision.module.startup_safe is False
