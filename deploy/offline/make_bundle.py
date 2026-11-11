"""Build a staged, provenance-recorded offline bundle on the connected build host."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CONFIG_FILES = ("compose.yaml", "env.example", "env.windows.example", "db-entrypoint.sh",
                "init-runtime-role.sh", "verify_bundle.py", "backup_restore.py", "README.md", "WINDOWS.md")
FIXED_INPUTS = ("backend/requirements.lock", "backend/alembic.ini", "frontend/package.json",
                "frontend/package-lock.json", "frontend/index.html", "frontend/tsconfig.json",
                "frontend/vite.config.ts", "deploy/offline/Dockerfile.app", "deploy/offline/runtime.py",
                "deploy/offline/permissions.py", "deploy/offline/combined_app.py")


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


def build_inputs(root):
    files = {root / name for name in FIXED_INPUTS}
    for folder, suffixes in (("backend/wellspring", {".py"}), ("backend/migrations", {".py", ".mako"}),
                             ("frontend/src", {".ts", ".vue", ".css", ".svg", ".png", ".jpg", ".woff2"})):
        files.update(p for p in (root / folder).rglob("*") if p.is_file() and p.suffix in suffixes and "__pycache__" not in p.parts)
    for path in files:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"构建输入缺失或链接到仓库外：{path.relative_to(root)}")
        for parent in path.relative_to(root).parents:
            candidate = root / parent
            if candidate.is_symlink() or (hasattr(candidate, "is_junction") and candidate.is_junction()):
                raise ValueError("构建输入不能经过链接目录")
    return sorted(files)


def project_version(root):
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    version = package["version"]
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or lock["version"] != version or lock["packages"][""]["version"] != version:
        raise ValueError("前端产品版本和锁文件不一致")
    main = (root / "backend/wellspring/main.py").read_text(encoding="utf-8-sig")
    if not re.search(r'version\s*=\s*["\x27]' + re.escape(version) + r'["\x27]', main):
        raise ValueError("后端产品版本不一致")
    return version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-base", required=True, type=digest_reference)
    parser.add_argument("--node-base", required=True, type=digest_reference)
    parser.add_argument("--postgres", required=True, type=digest_reference)
    parser.add_argument("--platform", default="linux/amd64", choices=("linux/amd64", "linux/arm64"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("输出目录已存在，请选择新目录")
    version = project_version(ROOT)
    inputs = build_inputs(ROOT)
    pg_metadata = json.loads(docker("image", "inspect", args.postgres))[0]
    if f"{pg_metadata['Os']}/{pg_metadata['Architecture']}" != args.platform:
        raise SystemExit("PostgreSQL 镜像平台与目标不一致")
    pg_version = docker("run", "--rm", "--network", "none", "--entrypoint", "postgres", args.postgres, "--version")
    if not re.search(r"\b17\.", pg_version):
        raise SystemExit("此部署包只支持 PostgreSQL 17")
    app, db = f"wellspring/app:{version}", "wellspring/postgres:17-offline"
    source_hash = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="wellspring-build-") as temporary:
        staging = Path(temporary)
        for path in inputs:
            name = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            source_hash.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        subprocess.run(["docker", "build", "--platform", args.platform, "--file", str(staging / "deploy/offline/Dockerfile.app"),
                        "--build-arg", f"PYTHON_BASE={args.python_base}", "--build-arg", f"NODE_BASE={args.node_base}",
                        "--tag", app, str(staging)], check=True)
    output.mkdir(parents=True)
    docker("tag", args.postgres, db)
    subprocess.run(["docker", "save", "--output", str(output / "images.tar"), app, db], check=True)
    for name in CONFIG_FILES:
        content = (HERE / name).read_text(encoding="utf-8")
        if name in {"compose.yaml", "env.example", "env.windows.example"}:
            content = re.sub(r"wellspring/app:[0-9]+\.[0-9]+\.[0-9]+", app, content)
        (output / name).write_text(content, encoding="utf-8", newline="\n")
    git_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    git_dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    manifest = {
        "schema_version": 2, "version": version,
        "build": {"created_at": datetime.now(timezone.utc).isoformat(), "platform": args.platform},
        "source": {"commit": git_commit.stdout.strip() if git_commit.returncode == 0 else None,
                   "dirty": bool(git_dirty.stdout) if git_dirty.returncode == 0 else None,
                   "build_inputs_sha256": source_hash.hexdigest(),
                   "python_lock_sha256": file_sha(ROOT / "backend/requirements.lock"),
                   "npm_lock_sha256": file_sha(ROOT / "frontend/package-lock.json")},
        "images": {name: docker("image", "inspect", "--format", "{{.Id}}", name) for name in (app, db)},
        "bases": {"python": args.python_base, "node": args.node_base, "postgres": args.postgres},
        "files": {name: file_sha(output / name) for name in ("images.tar", *CONFIG_FILES)},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("离线包已生成：", output)
    print("manifest.json SHA-256:", file_sha(output / "manifest.json"))
    print("独立分发校验引导工具：", HERE / "trusted_verify.py")
    print("trusted_verify.py SHA-256:", file_sha(HERE / "trusted_verify.py"))
    print("请通过独立可信渠道传递此摘要和校验步骤；校验脚本通过可信工具核验前禁止执行。")


if __name__ == "__main__":
    main()
