"""浏览器回归专用 API：全新临时库、合成账号，不读取项目 .env。"""
import os
from pathlib import Path
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "backend"))
    with tempfile.TemporaryDirectory(prefix="wellspring-e2e-") as folder:
        os.environ["DATABASE_URL"] = "sqlite:///" + (Path(folder) / "test.db").as_posix()
        from alembic import command
        from alembic.config import Config
        config = Config(str(root / "backend" / "alembic.ini"))
        config.set_main_option("script_location", str(root / "backend" / "migrations"))
        command.upgrade(config, "head")
        from wellspring.db import SessionLocal
        from wellspring.models import Organization, User
        from wellspring.security import password_hash
        with SessionLocal() as db:
            org = Organization(name="浏览器回归组织")
            other = Organization(name="隔离组织")
            db.add_all([org, other])
            db.flush()
            encoded = password_hash("synthetic-test-password")
            db.add_all([User(username=name, org_id=organization.id, password_hash=encoded)
                        for name, organization in (("alice", org), ("receiver", org), ("outsider", other))])
            db.add(User(username="superadmin",org_id=org.id,password_hash=encoded,is_admin=True))
            db.commit()
        import uvicorn
        uvicorn.run("wellspring.main:app", host="127.0.0.1", port=8419, log_level="warning")


if __name__ == "__main__":
    main()
