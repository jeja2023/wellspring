"""Development-only custody baseline and two-party handovers."""
from alembic import op
import sqlalchemy as sa
revision="0013"
down_revision="0012"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("evidence_custody",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("evidence_id",sa.String(36),sa.ForeignKey("evidence.id"),nullable=False),sa.Column("custodian_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("evidence_id",name="uq_evidence_custody_evidence"))
    for col in ("org_id","evidence_id"):op.create_index("ix_evidence_custody_"+col,"evidence_custody",[col])
    op.create_table("custody_handovers",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("evidence_id",sa.String(36),sa.ForeignKey("evidence.id"),nullable=False),sa.Column("from_user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("to_user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("custody_version",sa.Integer(),nullable=False),sa.Column("status",sa.String(20),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("note",sa.Text(),nullable=False),sa.Column("response_note",sa.Text(),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("responded_at",sa.DateTime(timezone=True),nullable=True))
    for col in ("org_id","evidence_id"):op.create_index("ix_custody_handovers_"+col,"custody_handovers",[col])
    op.create_index("uq_custody_handover_pending","custody_handovers",["evidence_id"],unique=True,sqlite_where=sa.text("status = 'PENDING'"),postgresql_where=sa.text("status = 'PENDING'"))
    op.create_table("custody_events",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("evidence_id",sa.String(36),sa.ForeignKey("evidence.id"),nullable=False),sa.Column("handover_id",sa.String(36),sa.ForeignKey("custody_handovers.id"),nullable=True),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("action",sa.String(30),nullable=False),sa.Column("note",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    for col in ("org_id","evidence_id"):op.create_index("ix_custody_events_"+col,"custody_events",[col])

def downgrade():
    op.drop_table("custody_events")
    op.drop_table("custody_handovers")
    op.drop_table("evidence_custody")
