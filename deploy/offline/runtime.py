"""从挂载的密钥文件构造数据库连接，再启动指定进程。"""
import os
from pathlib import Path
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from permissions import apply_runtime_permissions


def read_password(path):
    raw = Path(path).read_bytes()
    if raw.endswith(b"\r\n"):
        raw = raw[:-2]
    elif raw.endswith(b"\n"):
        raw = raw[:-1]
    if not raw or raw.startswith(b"\xef\xbb\xbf") or any(c in raw for c in (b"\r", b"\n", b"\x00")):
        raise ValueError("数据库密码文件须为 UTF-8 无 BOM 单行，可带一个 LF 或 CRLF 结尾")
    return raw.decode("utf-8")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "api"
    try:
        password = read_password(os.environ["DB_PASSWORD_FILE"])
    except (OSError, ValueError):
        raise SystemExit("数据库密码文件为空或格式无效") from None
    url = URL.create(
        "postgresql+psycopg", username=os.environ["DB_USER"], password=password,
        host=os.environ.get("DB_HOST", "db"), port=5432,
        database=os.environ.get("DB_NAME", "wellspring"),
    )
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    if action == "api":
        os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "combined_app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"])
    if action == "migrate":
        from alembic import command
        from alembic.config import Config
        command.upgrade(Config("alembic.ini"), "head")
        # 默认权限不能区分审计表；每次迁移后显式收紧。
        engine = create_engine(url)
        with engine.begin() as connection:
            apply_runtime_permissions(connection)
        engine.dispose()
        return
    if action == "bootstrap":
        from wellspring.bootstrap import main as bootstrap
        if sys.argv[2:] not in ([], ["--initial-admin"]):
            raise SystemExit("未知账号初始化参数")
        bootstrap(initial_admin=sys.argv[2:] == ["--initial-admin"])
        return
    raise SystemExit("未知操作")

if __name__ == "__main__":
    main()
