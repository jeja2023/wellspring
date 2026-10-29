"""在联网构建机制作可转移的离线镜像包；不在目标机器运行构建。"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CONFIG_FILES = ("compose.yaml", "env.example", "init-runtime-role.sh", "verify_bundle.py", "README.md")


def digest_reference(value):
    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("必须使用镜像名@sha256:完整摘要")
    return value


def docker(*args):
    return subprocess.run(["docker", *args], check=True, text=True, capture_output=True).stdout.strip()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-base", required=True, type=digest_reference)
    parser.add_argument("--node-base", required=True, type=digest_reference)
    parser.add_argument("--nginx-base", required=True, type=digest_reference)
    parser.add_argument("--postgres", required=True, type=digest_reference)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("输出目录已存在，请选择新目录，避免覆盖已有交付物")
    # PostgreSQL 镜像应先按摘要取得并审核；构建输出镜像在本机构建。
    docker("image", "inspect", args.postgres)
    version = docker("run", "--rm", "--network", "none", "--entrypoint", "postgres", args.postgres, "--version")
    if not re.search(r"\b17\.", version):
        raise SystemExit("此部署包只支持 PostgreSQL 17，请选择已审核的 17 系列镜像")
    output.mkdir(parents=True)
    api, web, db = "wellspring/api:0.0.2", "wellspring/web:0.0.2", "wellspring/postgres:17-offline"
    subprocess.run(["docker", "build", "--file", str(HERE / "Dockerfile.api"), "--build-arg", f"PYTHON_BASE={args.python_base}", "--tag", api, str(ROOT)], check=True)
    subprocess.run(["docker", "build", "--file", str(HERE / "Dockerfile.web"), "--build-arg", f"NODE_BASE={args.node_base}", "--build-arg", f"NGINX_BASE={args.nginx_base}", "--tag", web, str(ROOT)], check=True)
    docker("tag", args.postgres, db)
    subprocess.run(["docker", "save", "--output", str(output / "images.tar"), api, web, db], check=True)
    for name in CONFIG_FILES:
        shutil.copy2(HERE / name, output / name)
    images = {name: docker("image", "inspect", "--format", "{{.Id}}", name) for name in (api, web, db)}
    manifest = {"images": images, "bases": {"python": args.python_base, "node": args.node_base, "nginx": args.nginx_base, "postgres": args.postgres}, "files": {}}
    for name in ("images.tar", *CONFIG_FILES):
        manifest["files"][name] = file_sha(output / name)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text("".join(f"{file_sha(output / name)}  {name}\n" for name in ("manifest.json", "images.tar", *CONFIG_FILES)), encoding="utf-8")
    print("离线包已生成：", output)
    print("manifest.json SHA-256:", file_sha(output / "manifest.json"))
    print("请通过独立可信渠道传递并核验此摘要；再按 README 在隔离环境导入。")

if __name__ == "__main__":
    main()
