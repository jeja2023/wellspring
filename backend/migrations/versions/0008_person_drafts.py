"""Add minimal, unverified person drafts for development."""
from alembic import op
import sqlalchemy as sa
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("person_drafts",sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),
        sa.Column("name",sa.String(120),nullable=False),sa.Column("source",sa.String(200),nullable=False),
        sa.Column("verification_status",sa.String(30),nullable=False),
        sa.Column("created_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("version",sa.Integer(),nullable=False))
    op.create_index("ix_person_drafts_org_id","person_drafts",["org_id"])

def downgrade():
    op.drop_table("person_drafts")
