"""Add same-organization case relations and events."""
from alembic import op
import sqlalchemy as sa
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("case_relations",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("source_case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),sa.Column("target_case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),sa.Column("relation_type",sa.String(30),nullable=False),sa.Column("relation_status",sa.String(20),nullable=False),sa.Column("basis",sa.Text(),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("revoked_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),sa.Column("revoked_at",sa.DateTime(timezone=True),nullable=True),sa.Column("revoke_reason",sa.Text(),nullable=True))
    for col in ("org_id","source_case_id","target_case_id"): op.create_index("ix_case_relations_"+col,"case_relations",[col])
    op.create_index("uq_case_relation_active","case_relations",["source_case_id","target_case_id","relation_type"],unique=True,sqlite_where=sa.text("relation_status = 'ACTIVE'"),postgresql_where=sa.text("relation_status = 'ACTIVE'"))
    op.create_table("case_relation_events",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("relation_id",sa.String(36),sa.ForeignKey("case_relations.id"),nullable=False),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("action",sa.String(30),nullable=False),sa.Column("before_status",sa.String(20),nullable=True),sa.Column("after_status",sa.String(20),nullable=False),sa.Column("note",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_case_relation_events_org_id","case_relation_events",["org_id"])
    op.create_index("ix_case_relation_events_relation_id","case_relation_events",["relation_id"])

def downgrade():
    op.drop_table("case_relation_events")
    op.drop_table("case_relations")
