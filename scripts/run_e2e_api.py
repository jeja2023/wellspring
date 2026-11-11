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
        # Browser suites reuse synthetic accounts; do not alter runtime defaults.
        os.environ['WELLSPRING_LOGIN_ACCOUNT_LIMIT'] = '1000'
        os.environ['WELLSPRING_LOGIN_IP_LIMIT'] = '1000'
        from alembic import command
        from alembic.config import Config
        config = Config(str(root / "backend" / "alembic.ini"))
        config.set_main_option("script_location", str(root / "backend" / "migrations"))
        command.upgrade(config, "head")
        from wellspring.db import SessionLocal
        from wellspring.models import Organization, User
        from wellspring.security import password_hash
        from wellspring.ai_models import AiService
        from mock_model_service import start_mock_model
        server, _ = start_mock_model()
        os.environ['WELLSPRING_AI_ALLOWED_HOSTS'] = '127.0.0.1'
        os.environ['WELLSPRING_AI_SECRET_DIR'] = str(Path(folder) / 'model-secrets')
        os.environ.pop('WELLSPRING_AI_API_KEY', None)
        os.environ.pop('WELLSPRING_AI_API_KEY_FILE', None)
        with SessionLocal() as db:
            org = Organization(name="浏览器回归组织")
            other = Organization(name="隔离组织")
            db.add_all([org, other])
            db.flush()
            encoded = password_hash("synthetic-test-password")
            db.add_all([User(username=name, org_id=organization.id, password_hash=encoded)
                        for name, organization in (("alice", org), ("receiver", org), ("outsider", other))])
            db.add(User(username="superadmin",org_id=org.id,password_hash=encoded,is_admin=True))
            service = db.get(AiService, 'primary')
            service.enabled = True
            service.base_url = f'http://127.0.0.1:{server.server_port}/v1'
            service.model = 'synthetic-model'
            db.commit()
        import uvicorn
        try:
            uvicorn.run("wellspring.main:app", host="127.0.0.1", port=8419, log_level="warning")
        finally:
            server.shutdown(); server.server_close()


if __name__ == "__main__":
    main()
