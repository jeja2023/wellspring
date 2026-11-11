"""Regressions for untrusted packages, secret normalization and deployment boundaries."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "offline"


def load(name):
    spec = importlib.util.spec_from_file_location("audit_" + name, DEPLOY / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle(tmp_path):
    verifier = load("verify_bundle")
    folder = tmp_path / "bundle with spaces"
    folder.mkdir()
    for name in verifier.EXPECTED:
        (folder / name).write_bytes(b"synthetic fixture\n")
    (folder / "verify_bundle.py").write_bytes((DEPLOY / "verify_bundle.py").read_bytes())
    manifest = {"schema_version": 2, "version": "0.0.4",
                "images": {"wellspring/app:0.0.4": "sha256:" + "1" * 64, "wellspring/postgres:17-offline": "sha256:" + "2" * 64},
                "files": {name: verifier.sha(folder / name) for name in verifier.EXPECTED}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder, verifier.sha(folder / "manifest.json")


def bootstrap(folder, digest, **kwargs):
    return subprocess.run([sys.executable, "-I", str(DEPLOY / "trusted_verify.py"), str(folder), "--manifest-sha256", digest], capture_output=True, **kwargs)


def test_trusted_bootstrap_accepts_valid_package_and_ignores_module_shadowing(tmp_path):
    folder, digest = bundle(tmp_path)
    marker = folder / "executed.txt"
    for name in ("json.py", "hashlib.py", "sitecustomize.py"):
        (folder / name).write_text(f"open({str(marker)!r}, 'w').write('executed')\nraise RuntimeError('shadowed')", encoding="utf-8")
    result = bootstrap(folder, digest, cwd=folder, env={**os.environ, "PYTHONPATH": str(folder)})
    assert result.returncode == 0, result.stderr
    assert not marker.exists()


def test_bootstrap_rejects_modified_verifier_before_execution(tmp_path):
    folder, digest = bundle(tmp_path)
    marker = folder / "executed.txt"
    (folder / "verify_bundle.py").write_text(f"open({str(marker)!r}, 'w').write('executed')", encoding="utf-8")
    result = bootstrap(folder, digest)
    assert result.returncode != 0
    assert b"Verifier hash mismatch" in result.stderr
    assert not marker.exists()


def test_bootstrap_rejects_modified_payload_and_manifest(tmp_path):
    folder, digest = bundle(tmp_path)
    (folder / "images.tar").write_bytes(b"changed")
    assert bootstrap(folder, digest).returncode != 0
    (folder / "manifest.json").write_text("{}", encoding="utf-8")
    result = bootstrap(folder, digest)
    assert result.returncode != 0 and b"Manifest hash mismatch" in result.stderr


def test_verifier_rejects_path_traversal_in_authenticated_manifest(tmp_path):
    folder, _ = bundle(tmp_path)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["../escape"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    verifier = load("verify_bundle")
    with pytest.raises(ValueError, match="文件列表"):
        verifier.verify(folder, verifier.sha(manifest_path))


@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_runtime_password_preserves_spaces_and_normalizes_one_line_ending(tmp_path, monkeypatch, ending):
    monkeypatch.syspath_prepend(str(DEPLOY))
    runtime = load("runtime")
    secret = tmp_path / "secret"
    secret.write_bytes(" 中文 synthetic #:@ ".encode() + ending)
    assert runtime.read_password(secret) == " 中文 synthetic #:@ "


@pytest.mark.parametrize("value", [b"", b"\n", b"abc\n\n", b"abc\r", b"a\nb", b"a\x00b", b"\xef\xbb\xbfabc", b"\xff"])
def test_runtime_password_rejects_ambiguous_or_invalid_bytes(tmp_path, monkeypatch, value):
    monkeypatch.syspath_prepend(str(DEPLOY))
    secret = tmp_path / "secret"
    secret.write_bytes(value)
    with pytest.raises(ValueError):
        load("runtime").read_password(secret)


@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_postgres_wrapper_and_python_parse_identical_passwords(tmp_path, monkeypatch, ending):
    bash = Path(r"C:\Program Files\Git\bin\bash.exe") if os.name == "nt" else Path(shutil.which("bash") or "/missing/bash")
    if not bash.is_file():
        pytest.skip("Bash is not installed")
    probe = subprocess.run([str(bash), "-c", "exit 0"], capture_output=True)
    if probe.returncode:
        pytest.skip("Bash cannot start in this environment")
    secret, normalized = tmp_path / "secret", tmp_path / "normalized"
    secret.write_bytes(" 中文 synthetic #:@ ".encode() + ending)
    result = subprocess.run([str(bash), "-c", 'source "$1"; normalize_secret "$2" "$3"', "--",
                             (DEPLOY / "db-entrypoint.sh").as_posix(), secret.as_posix(), normalized.as_posix()], capture_output=True)
    assert result.returncode == 0, result.stderr
    monkeypatch.syspath_prepend(str(DEPLOY))
    assert normalized.read_text(encoding="utf-8") == load("runtime").read_password(secret)


def test_permissions_cover_all_business_tables_without_unsafe_identifiers():
    from wellspring.db import Base
    from wellspring import models
    permissions = load("permissions")
    assert permissions.APPEND_ONLY_TABLES | permissions.MUTABLE_TABLES | set(permissions.RESTRICTED_UPDATE_TABLES) | {"sessions"} == set(Base.metadata.tables)
    with pytest.raises(ValueError):
        permissions.apply_runtime_permissions(None, role='x; DROP SCHEMA public')


def test_staged_build_excludes_local_databases_secrets_and_reports():
    build = load("make_bundle")
    names = {path.relative_to(ROOT).as_posix() for path in build.build_inputs(ROOT)}
    assert "backend/requirements.lock" in names
    assert "deploy/offline/permissions.py" in names
    assert not any(name.startswith(("backend/backups/", "releases/", "frontend/test-results/", "frontend/playwright-report/")) for name in names)
    assert not any(Path(name).name.startswith(".env") for name in names)


def test_restore_refuses_digest_mismatch_before_starting_docker(tmp_path, monkeypatch):
    backup = load("backup_restore")
    dump = tmp_path / "test.dump"
    dump.write_bytes(b"synthetic")
    monkeypatch.setattr(backup, "run", lambda *a, **k: pytest.fail("Docker must not run"))
    with pytest.raises(ValueError, match="摘要"):
        backup.drill(dump, "image", "0" * 64, tmp_path / "report.json")


def test_failed_backup_leaves_no_final_or_partial_dump(tmp_path, monkeypatch):
    backup = load("backup_restore")
    config = tmp_path / "config.env"
    config.write_text("synthetic")
    output = tmp_path / "backup.dump"
    def fake_run(command, **kwargs):
        if "psql" in command:
            return subprocess.CompletedProcess(command, 0, stdout="170002\n")
        kwargs["stdout"].write(b"partial dump")
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(backup, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        backup.backup(config, output)
    assert not output.exists()
    assert not list(tmp_path.glob("*.partial"))
    assert not list(tmp_path.glob("*.sha256"))


def test_completed_backup_publishes_matching_digest_without_overwrite(tmp_path, monkeypatch):
    backup = load("backup_restore")
    config = tmp_path / "config.env"
    config.write_text("synthetic")
    output = tmp_path / "backup.dump"
    def fake_run(command, **kwargs):
        if "psql" in command:
            return subprocess.CompletedProcess(command, 0, stdout="170002\n")
        kwargs["stdout"].write(b"complete dump")
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(backup, "run", fake_run)
    backup.backup(config, output)
    assert output.read_bytes() == b"complete dump"
    assert output.with_suffix(".dump.sha256").read_text().startswith(hashlib.sha256(b"complete dump").hexdigest())
    with pytest.raises(ValueError, match="已存在"):
        backup.backup(config, output)


def test_loaded_verification_never_resolves_docker_from_bundle(tmp_path, monkeypatch):
    verifier = load("verify_bundle")
    folder, _ = bundle(tmp_path)
    filename = "docker.exe" if os.name == "nt" else "docker"
    (folder / filename).write_bytes(b"not executable")
    monkeypatch.setenv("PATH", str(folder))
    with pytest.raises(ValueError, match="Docker"):
        verifier.docker_executable(folder)
