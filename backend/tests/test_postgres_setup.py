"""Account validation must fail before any local PostgreSQL resource is created."""
import importlib.util
from pathlib import Path
import pytest


@pytest.mark.parametrize("password", ["x" * 11, "x" * 257])
def test_setup_rejects_invalid_application_password_before_connecting(tmp_path, monkeypatch, password):
    path = Path(__file__).resolve().parents[2] / "setup_postgres.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("audit_setup", path)
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    monkeypatch.setattr(setup, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(setup, "LEGACY_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr("builtins.input", lambda _: "postgres")
    answers = iter(["synthetic-admin", "synthetic-role", "synthetic-role", password])
    monkeypatch.setattr(setup.getpass, "getpass", lambda _: next(answers))
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda **_: pytest.fail("invalid credentials must not touch any server"))
    with pytest.raises(SystemExit, match="12–256"):
        setup.main()
