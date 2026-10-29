"""Create one development account. Never use this command with production data."""
import getpass
from sqlalchemy import select
from .db import SessionLocal
from .models import Organization, User
from .security import password_hash

def main():
    username = input("开发账号: ").strip()
    org_name = input("开发组织: ").strip()
    password = getpass.getpass("密码（至少 12 位）: ")
    if not username or not org_name or len(password) < 12: raise SystemExit("输入无效")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)): raise SystemExit("账号已存在")
        org = db.scalar(select(Organization).where(Organization.name == org_name))
        if not org:
            org = Organization(name=org_name); db.add(org); db.flush()
        db.add(User(username=username, org_id=org.id, password_hash=password_hash(password)))
        db.commit()
    print("开发账号已创建。")
if __name__ == "__main__": main()
