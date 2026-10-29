"""核验离线包文件，或在导入后核验镜像 ID。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
EXPECTED = {"images.tar", "compose.yaml", "env.example", "init-runtime-role.sh", "verify_bundle.py", "README.md"}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loaded", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if set(manifest["files"]) != EXPECTED:
        raise SystemExit("清单文件列表异常")
    for name, expected in manifest["files"].items():
        if sha(ROOT / name) != expected:
            raise SystemExit(f"校验失败: {name}")
    if args.loaded:
        expected_images = {"wellspring/api:0.0.4", "wellspring/web:0.0.4", "wellspring/postgres:17-offline"}
        if set(manifest["images"]) != expected_images:
            raise SystemExit("镜像清单异常")
        for name, expected in manifest["images"].items():
            actual = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", name], check=True, text=True, capture_output=True).stdout.strip()
            if actual != expected:
                raise SystemExit(f"镜像 ID 不匹配: {name}")
    print("核验通过" + ("，镜像 ID 一致" if args.loaded else ""))

if __name__ == "__main__":
    main()
