"""Assign the initial admin to a dedicated system operations organization."""
from datetime import datetime, timezone
from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    admin = connection.execute(sa.text("SELECT id, org_id FROM users WHERE username = :username AND is_admin = :is_admin"), {"username": "admin", "is_admin": True}).mappings().first()
    if not admin:
        return
    org = connection.execute(sa.text("SELECT id FROM organizations WHERE name = :name"), {"name": "系统运维"}).first()
    org_id = org[0] if org else str(uuid4())
    if not org:
        connection.execute(sa.text("INSERT INTO organizations (id, name) VALUES (:id, :name)"), {"id": org_id, "name": "系统运维"})
    if admin["org_id"] != org_id:
        connection.execute(sa.text("UPDATE users SET org_id = :org_id WHERE id = :user_id"), {"org_id": org_id, "user_id": admin["id"]})
        connection.execute(sa.text("INSERT INTO audit_events (id, actor_id, org_id, action, object_id, created_at) VALUES (:id, :actor_id, :org_id, :action, :object_id, :created_at)"), {"id": str(uuid4()), "actor_id": admin["id"], "org_id": org_id, "action": "INITIAL_ADMIN_ORGANIZATION_ASSIGN", "object_id": admin["id"], "created_at": datetime.now(timezone.utc)})


def downgrade():
    raise RuntimeError("此迁移涉及管理员组织归属，请按备份和人工确认的原归属恢复。")
