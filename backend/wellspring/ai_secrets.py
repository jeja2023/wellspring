"""Immutable server-only credential files, referenced transactionally by configuration."""
import os
from pathlib import Path
import re
from uuid import uuid4

NO_KEY = "NONE"


def directory():
    return Path(os.getenv("WELLSPRING_AI_SECRET_DIR", str(Path(__file__).resolve().parents[1] / ".secrets"))).resolve()


def secret_path(reference):
    if not isinstance(reference, str) or not re.fullmatch(r"[0-9a-f]{32}", reference):
        raise ValueError("Invalid credential reference")
    return directory() / (reference + ".key")


def store(value: str):
    root = directory()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    reference = uuid4().hex
    path = secret_path(reference)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value.encode("utf-8")); stream.flush(); os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return reference


def read(reference: str):
    if reference == NO_KEY:
        return ""
    path = secret_path(reference)
    if path.is_symlink() or path.stat().st_size > 16_384:
        raise ValueError("Invalid credential file")
    return path.read_text(encoding="utf-8")


def discard(reference: str):
    secret_path(reference).unlink(missing_ok=True)
