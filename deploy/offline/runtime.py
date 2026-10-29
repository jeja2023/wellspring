"""从挂载的密钥文件构造数据库连接，再启动指定进程。"""
import os
from pathlib import Path
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "api"
    password = Path(os.environ["DB_PASSWORD_FILE"]).read_text(encoding="utf-8").rstrip("\r\n")
    if not password or "\n" in password or "\r" in password or "\x00" in password:
        raise SystemExit("数据库密码文件为空或格式无效")
    url = URL.create(
        "postgresql+psycopg", username=os.environ["DB_USER"], password=password,
        host=os.environ.get("DB_HOST", "db"), port=5432,
        database=os.environ.get("DB_NAME", "wellspring"),
    )
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    if action == "api":
        os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "wellspring.main:app", "--host", "0.0.0.0", "--port", "8000"])
    if action == "migrate":
        from alembic import command
        from alembic.config import Config
        command.upgrade(Config("alembic.ini"), "head")
        # 默认权限不能区分审计表；每次迁移后显式收紧。
        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(text("REVOKE UPDATE, DELETE ON TABLE audit_events FROM wellspring_app"))
            connection.execute(text("REVOKE UPDATE, DELETE ON TABLE intelligence_events FROM wellspring_app"))
            connection.execute(text("GRANT DELETE ON TABLE sessions TO wellspring_app"))
        engine.dispose()
        return
    if action == "bootstrap":
        from wellspring.bootstrap import main as bootstrap
        bootstrap()
        return
    raise SystemExit("未知操作")

if __name__ == "__main__":
    main()
