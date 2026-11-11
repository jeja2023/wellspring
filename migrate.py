"""Database maintenance entry point for source checkouts; select the target by configuration."""
from __future__ import annotations

import os
import argparse
from pathlib import Path
import subprocess
import sys
from local_config import database_environment, database_target

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
VENV_PYTHON = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    parser = argparse.ArgumentParser(description="使用所选数据库配置执行迁移、结构检查或账号初始化")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只检查模型与迁移差异")
    mode.add_argument("--bootstrap", action="store_true", help="交互初始化本地账号")
    parser.add_argument("--initial-admin", action="store_true", help="与 --bootstrap 同用，创建首个管理员")
    args = parser.parse_args()
    if args.initial_admin and not args.bootstrap:
        parser.error("--initial-admin 必须与 --bootstrap 同用")
    try:
        env = database_environment(os.environ.copy())
        target = database_target(env)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"数据库配置无效：{error}")
    if not VENV_PYTHON.is_file():
        raise SystemExit("未找到 backend 虚拟环境，请先按 README 安装依赖")
    print(f"数据库目标：{target}", flush=True)
    if args.bootstrap:
        command = ["-m", "wellspring.bootstrap"] + (["--initial-admin"] if args.initial_admin else [])
    elif args.check:
        command = ["-m", "alembic", "check"]
    else:
        print("请确认已停止项目；已有数据库将先备份，再执行显式手动迁移…", flush=True)
        command = ["-m", "wellspring.startup_migrations", "--manual"]
    result = subprocess.run([str(VENV_PYTHON), *command], cwd=BACKEND, env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
