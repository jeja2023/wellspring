"""生成不包含本地数据、依赖及密钥的个人开发源码包。"""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXED = ["README.md", "更新日志.md", "清源·禁毒全流程协同平台v2.5.0.md", "效果图.png", "start.py", ".gitignore", ".gitattributes", ".dockerignore", "backend/alembic.ini", "backend/requirements.txt", "backend/requirements-dev.txt", "frontend/package.json", "frontend/package-lock.json", "frontend/index.html", "frontend/tsconfig.json", "frontend/vite.config.ts"]
TREES = {"backend/wellspring": {".py"}, "backend/migrations": {".py"}, "backend/tests": {".py"}, "frontend/src": {".ts", ".vue", ".css", ".svg"}, "frontend/tests": {".mjs"}, "docs": {".md"}, "deploy/offline": {".py", ".sh", ".yaml", ".md", ".conf"}, ".github/workflows": {".yml"}, "scripts": {".py"}}
EXTRA = ["deploy/offline/Dockerfile.api", "deploy/offline/Dockerfile.web", "deploy/offline/env.example"]


def main():
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    version = package["version"]
    if not re.fullmatch(r"0\.0\.[0-9]+", version):
        raise SystemExit("仅支持已确认的 0.0.x 开发版本")
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    if lock["version"] != version or lock["packages"][""]["version"] != version:
        raise SystemExit("前端版本和锁文件不一致")
    main_source = (ROOT / "backend/wellspring/main.py").read_text(encoding="utf-8-sig")
    if f'version="{version}"' not in main_source:
        raise SystemExit("后端版本与前端版本不一致")
    files = {ROOT / name for name in (*FIXED, *EXTRA)}
    for folder, extensions in TREES.items():
        files.update(p for p in (ROOT / folder).rglob("*") if p.is_file() and not p.is_symlink() and p.suffix in extensions and "__pycache__" not in p.parts)
    missing = [str(p.relative_to(ROOT)) for p in files if not p.is_file() or p.is_symlink()]
    if missing:
        raise SystemExit(f"必要文件缺失或为符号链接: {missing}")
    out = ROOT / "releases" / f"wellspring-{version}-source.zip"
    digest_file = out.with_suffix(out.suffix + ".sha256")
    if out.exists() or digest_file.exists():
        raise SystemExit("版本文件已存在，不会覆盖；需要新版本或明确处理旧交付物")
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
            name = p.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            archive.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    digest_file.write_text(f"{digest}  {out.name}\n", encoding="ascii")
    print(f"已生成 {out} ({len(files)} files)")
    print(f"SHA-256: {digest}")

if __name__ == "__main__":
    main()
