"""Initial development schema.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("organizations", sa.Column("id",sa.String(36),primary_key=True),sa.Column("name",sa.String(120),nullable=False,unique=True))
    op.create_table("users",sa.Column("id",sa.String(36),primary_key=True),sa.Column("username",sa.String(80),nullable=False),sa.Column("password_hash",sa.String(255),nullable=False),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("active",sa.Boolean(),nullable=False))
    op.create_index("ix_users_username","users",["username"],unique=True)
    op.create_table("sessions",sa.Column("token_hash",sa.String(64),primary_key=True),sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("cases",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("number",sa.String(80),nullable=False),sa.Column("title",sa.String(200),nullable=False),sa.Column("status",sa.String(40),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("org_id","number"))
    op.create_index("ix_cases_org_id","cases",["org_id"])
    op.create_table("evidence",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),sa.Column("parent_id",sa.String(36),sa.ForeignKey("evidence.id")),sa.Column("label",sa.String(200),nullable=False),sa.Column("balance",sa.Numeric(20,6),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_evidence_org_id","evidence",["org_id"])
    op.create_table("weight_events",sa.Column("id",sa.String(36),primary_key=True),sa.Column("operation_id",sa.String(36),nullable=False),sa.Column("evidence_id",sa.String(36),sa.ForeignKey("evidence.id"),nullable=False),sa.Column("kind",sa.String(30),nullable=False),sa.Column("delta",sa.Numeric(20,6),nullable=False),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("reason",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_weight_events_operation_id","weight_events",["operation_id"]); op.create_index("ix_weight_events_evidence_id","weight_events",["evidence_id"])
    op.create_table("audit_events",sa.Column("id",sa.String(36),primary_key=True),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("action",sa.String(80),nullable=False),sa.Column("object_id",sa.String(36),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_audit_events_org_id","audit_events",["org_id"])

def downgrade():
    for name in ("audit_events","weight_events","evidence","cases","sessions","users","organizations"): op.drop_table(name)
