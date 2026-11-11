"""本地 PostgreSQL 开发库一次性初始化；不用于生产。"""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import subprocess
import sys
from local_config import ENV_FILE, LEGACY_FILE, write_local_env

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
DATABASE = "wellspring"
ROLE = "wellspring"


def main():
    if ENV_FILE.exists() or LEGACY_FILE.exists():
        raise SystemExit("数据库配置已存在，未作修改。")
    try:
        import psycopg
        from psycopg import sql
        from sqlalchemy.engine import URL
    except ImportError:
        raise SystemExit("请使用 backend/.venv 中的 Python 执行此脚本。")
    sys.path.insert(0, str(BACKEND))
    from wellspring.credentials import NEW_PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH

    print("仅初始化本机虚构数据开发库；不会复制 SQLite 中的数据。")
    username = input("本机 PostgreSQL 管理员账号 [postgres]: ").strip() or "postgres"
    admin_password = getpass.getpass("PostgreSQL 管理员密码: ")
    if not admin_password: raise SystemExit("管理员密码不能为空。")
    role_password = getpass.getpass("新建数据库账号 wellspring 的密码: ")
    if not role_password: raise SystemExit("数据库账号密码不能为空。")
    if role_password != getpass.getpass("再次输入数据库账号密码: "): raise SystemExit("两次数据库密码不一致。")
    app_password = getpass.getpass("初始应用账号 admin 的密码: ")
    if not NEW_PASSWORD_MIN_LENGTH <= len(app_password) <= PASSWORD_MAX_LENGTH:
        raise SystemExit("应用账号密码须为 12–256 字符。")
    if app_password != getpass.getpass("再次输入应用账号密码: "): raise SystemExit("两次应用密码不一致。")
    try:
        with psycopg.connect(host="127.0.0.1", port=5432, dbname="postgres", user=username, password=admin_password, connect_timeout=5, autocommit=True) as conn:
            if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE,)).fetchone():
                raise SystemExit("数据库 wellspring 已存在；未覆盖，请先人工核查。")
            if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone():
                raise SystemExit("数据库账号 wellspring 已存在；未覆盖，请先人工核查。")
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS").format(sql.Identifier(ROLE), sql.Literal(role_password)))
            try:
                conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(DATABASE), sql.Identifier(ROLE)))
            except Exception:
                print("数据库创建失败；已创建的数据库账号保留，请人工核查后处理。", file=sys.stderr)
                raise
    except psycopg.Error as exc:
        raise SystemExit(f"PostgreSQL 连接或初始化失败：{exc.__class__.__name__}。请检查账号权限和服务。")

    url = URL.create("postgresql+psycopg", username=ROLE, password=role_password, host="127.0.0.1", port=5432, database=DATABASE)
    env = os.environ.copy()
    env["DATABASE_URL"] = url.render_as_string(hide_password=False)
    print("正在执行数据库迁移…", flush=True)
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env)
    if result.returncode: raise SystemExit("迁移失败；数据库和账号保留，请检查后处理。")
    sys.path.insert(0, str(BACKEND))
    os.environ["DATABASE_URL"] = env["DATABASE_URL"]
    from wellspring.db import SessionLocal
    from wellspring.models import Audit, Organization, User
    from wellspring.security import password_hash
    try:
        with SessionLocal() as db:
            org = Organization(name="系统运维")
            db.add(org); db.flush()
            user = User(username="admin", org_id=org.id, password_hash=password_hash(app_password), is_admin=True)
            db.add(user); db.flush()
            db.add(Audit(actor_id=user.id, org_id=org.id, action="INITIAL_ADMIN_ASSIGN", object_id=user.id))
            db.commit()
    except Exception:
        raise SystemExit("应用管理员创建失败；数据库和账号保留，请检查后处理。")
    write_local_env("127.0.0.1", 5432, DATABASE, ROLE, password=role_password)
    print("开发数据库及初始管理员已创建。数据库密码保存在本机 .env；今后使用 python start.py 启动。")


if __name__ == "__main__":
    main()
