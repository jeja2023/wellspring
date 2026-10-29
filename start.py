"""一键启动本地开发服务；按 Ctrl+C 停止本脚本创建的进程。"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PYTHON = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
VITE = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
MIGRATION_CHECK = """from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from pathlib import Path
from wellspring.db import engine
if engine.url.get_backend_name() == 'sqlite':
    database = engine.url.database
    if database and database != ':memory:' and not Path(database).is_file():
        raise SystemExit('开发数据库不存在，请先在 backend 目录执行 python -m alembic upgrade head')
config = Config('alembic.ini')
expected = set(ScriptDirectory.from_config(config).get_heads())
with engine.connect() as connection:
    current = set(MigrationContext.configure(connection).get_current_heads())
if current != expected:
    raise SystemExit('数据库迁移尚未完成，请先在 backend 目录执行 python -m alembic upgrade head')
"""


def free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def wait_ready(url: str, process: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"服务启动失败，进程退出码：{process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.2)
    raise RuntimeError(f"服务启动超时：{url}")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.wait(timeout=5)
            return
        except (OSError, subprocess.TimeoutExpired):
            # 仅结束本启动器创建的进程及其子进程。
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="一键启动清源本地开发服务")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    args = parser.parse_args()
    if any(port < 1 or port > 65535 for port in (args.backend_port, args.frontend_port)):
        print("端口必须在 1 至 65535 之间。", file=sys.stderr)
        return 1
    if args.backend_port == args.frontend_port:
        print("前端和后端端口不能相同。", file=sys.stderr)
        return 1
    node = shutil.which("node")
    if not VENV_PYTHON.exists() or not VITE.exists() or not node:
        print("依赖尚未准备，请参照 README 中的首次安装步骤。", file=sys.stderr)
        return 1
    for port in (args.backend_port, args.frontend_port):
        if not free_port(port):
            print(f"端口 {port} 已被占用；请先停止占用该端口的服务，或指定其他端口。", file=sys.stderr)
            return 1
    check = subprocess.run([str(VENV_PYTHON), "-c", MIGRATION_CHECK], cwd=BACKEND)
    if check.returncode != 0:
        return 1
    env = os.environ.copy()
    env["VITE_API_TARGET"] = f"http://127.0.0.1:{args.backend_port}"
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    children: list[subprocess.Popen] = []
    try:
        print("正在启动后端…", flush=True)
        backend = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "uvicorn", "wellspring.main:app", "--host", "127.0.0.1", "--port", str(args.backend_port)],
            cwd=BACKEND, env=env, creationflags=flags, start_new_session=os.name != "nt",
        )
        children.append(backend)
        wait_ready(f"http://127.0.0.1:{args.backend_port}/api/health", backend)
        print("正在启动前端…", flush=True)
        frontend = subprocess.Popen(
            [node, str(VITE), "--host", "127.0.0.1", "--port", str(args.frontend_port), "--strictPort"],
            cwd=FRONTEND, env=env, creationflags=flags, start_new_session=os.name != "nt",
        )
        children.append(frontend)
        wait_ready(f"http://127.0.0.1:{args.frontend_port}/", frontend)
        print(f"\n启动成功： http://127.0.0.1:{args.frontend_port}/", flush=True)
        print("保持本窗口打开；按 Ctrl+C 停止前后端。", flush=True)
        while True:
            for name, child in (("后端", backend), ("前端", frontend)):
                if child.poll() is not None:
                    raise RuntimeError(f"{name}已退出，退出码：{child.returncode}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在停止服务…", flush=True)
        return 0
    except (RuntimeError, OSError) as exc:
        print(f"启动或运行失败：{exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        for child in reversed(children):
            stop_process(child)


if __name__ == "__main__":
    raise SystemExit(main())
