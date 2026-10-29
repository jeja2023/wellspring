"""Append-only evidence inventory observations."""
from alembic import op
import sqlalchemy as sa
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("evidence_inventory_observations",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),
        sa.Column("evidence_id",sa.String(36),sa.ForeignKey("evidence.id"),nullable=False),
        sa.Column("book_weight",sa.Numeric(20,6),nullable=False),
        sa.Column("observed_weight",sa.Numeric(20,6),nullable=False),
        sa.Column("difference",sa.Numeric(20,6),nullable=False),
        sa.Column("evidence_version",sa.Integer(),nullable=False),
        sa.Column("note",sa.Text(),nullable=False),
        sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_evidence_inventory_observations_org_id","evidence_inventory_observations",["org_id"])
    op.create_index("ix_evidence_inventory_observations_evidence_id","evidence_inventory_observations",["evidence_id"])

def downgrade():
    op.drop_table("evidence_inventory_observations")
