"""Run only after this file is verified by the trusted bootstrap instructions."""
import sys

if __name__ == "__main__" and not sys.flags.isolated:
    raise SystemExit("Run with python -I; untrusted bundle modules must not be imported")

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
EXPECTED = {"images.tar", "compose.yaml", "env.example", "env.windows.example",
            "db-entrypoint.sh", "init-runtime-role.sh", "verify_bundle.py",
            "backup_restore.py", "README.md", "WINDOWS.md"}


def docker_executable(root):
    # Windows CreateProcess searches cwd before PATH for a bare executable name.
    # Resolve an absolute executable outside the bundle before launching it.
    filename = "docker.exe" if os.name == "nt" else "docker"
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        path = Path(directory)
        if not path.is_absolute() or path.resolve().is_relative_to(root.resolve()):
            continue
        candidate = (path / filename).resolve()
        if candidate.is_file() and not candidate.is_relative_to(root.resolve()) and os.access(candidate, os.X_OK):
            return str(candidate)
    raise ValueError("未找到包外可信 PATH 中的 Docker 可执行文件")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest key")
        result[key] = value
    return result


def regular_file(root, name):
    path = root / name
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()) or not path.is_file() or path.resolve().parent != root.resolve():
        raise ValueError(f"Not a regular bundle file: {name}")
    return path


def verify(root, expected_manifest_sha, loaded=False):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_manifest_sha):
        raise ValueError("必须指定独立可信渠道取得的 manifest SHA-256")
    manifest_path = regular_file(root, "manifest.json")
    if not hmac.compare_digest(sha(manifest_path), expected_manifest_sha.lower()):
        raise ValueError("manifest 摘要不匹配")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)
    if manifest.get("schema_version") != 2 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest.get("version", "")):
        raise ValueError("不支持的清单格式或版本")
    if set(manifest["files"]) != EXPECTED:
        raise ValueError("清单文件列表异常")
    expected_images = {f"wellspring/app:{manifest['version']}", "wellspring/postgres:18-offline"}
    if set(manifest["images"]) != expected_images:
        raise ValueError("镜像清单异常")
    for name, expected in manifest["files"].items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or not hmac.compare_digest(sha(regular_file(root, name)), expected):
            raise ValueError(f"校验失败: {name}")
    for name, expected in manifest["images"].items():
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
            raise ValueError("镜像 ID 格式无效")
        if loaded:
            actual = subprocess.run([docker_executable(root), "image", "inspect", "--format", "{{.Id}}", name], check=True, text=True, capture_output=True).stdout.strip()
            if actual != expected:
                raise ValueError(f"镜像 ID 不匹配: {name}")
    return manifest


def main():
    if not sys.flags.isolated:
        raise SystemExit("必须使用 python -I 运行，防止包内模块/PYTHONPATH 覆盖标准库")
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--loaded", action="store_true")
    args = parser.parse_args()
    try:
        verify(ROOT, args.manifest_sha256, args.loaded)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"核验失败：{error}") from None
    print("核验通过" + ("，镜像 ID 一致" if args.loaded else ""))


if __name__ == "__main__":
    main()
