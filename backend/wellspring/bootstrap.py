"""Create one development account. Never use this command with production data."""
import getpass
import argparse
from sqlalchemy import select
from .db import SessionLocal
from .models import Audit, Organization, User
from .security import NEW_PASSWORD_MIN_LENGTH, ORGANIZATION_MAX_LENGTH, PASSWORD_MAX_LENGTH, USERNAME_MAX_LENGTH, password_hash
from .access_models import Role
from .access_policy import DEFAULT_ROLE_ID

def main(initial_admin=False):
    username = input("开发账号: ").strip()
    org_name = "系统运维" if initial_admin else input("开发组织: ").strip()
    password = getpass.getpass("密码（至少 12 位）: ")
    if not 1 <= len(username) <= USERNAME_MAX_LENGTH or not 1 <= len(org_name) <= ORGANIZATION_MAX_LENGTH or not NEW_PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise SystemExit("账号须为 1–80 字符，组织须为 1–120 字符，密码须为 12–256 字符")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)): raise SystemExit("账号已存在")
        if initial_admin and db.scalar(select(User.id).where(User.is_admin.is_(True))): raise SystemExit("已存在管理员，不能重复创建初始管理员")
        org = db.scalar(select(Organization).where(Organization.name == org_name))
        if not org:
            org = Organization(name=org_name); db.add(org); db.flush()
        role=db.get(Role,DEFAULT_ROLE_ID)
        if role and not role.active and not initial_admin:raise SystemExit("默认业务角色已停用，请由管理员通过用户管理创建账号")
        user = User(username=username, org_id=org.id, password_hash=password_hash(password), is_admin=initial_admin,role_id=role.id if role and not initial_admin else None)
        db.add(user)
        if initial_admin:
            db.flush()
            db.add(Audit(actor_id=user.id, org_id=org.id, action="INITIAL_ADMIN_ASSIGN", object_id=user.id))
        db.commit()
    print("开发账号已创建。" + ("已设为初始管理员。" if initial_admin else ""))
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--initial-admin', action='store_true')
    main(initial_admin=parser.parse_args().initial_admin)
