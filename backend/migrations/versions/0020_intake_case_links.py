"""Traceable intake-to-case links with immutable source snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None
startup_safe = True  # Additive relation table; existing records remain independent.


def upgrade():
    op.create_table("intake_case_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("intake_id", sa.String(36), sa.ForeignKey("case_information.id"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False), sa.Column("source_number", sa.String(80), nullable=False),
        sa.Column("source_snapshot", sa.Text(), nullable=False), sa.Column("created_case", sa.Boolean(), nullable=False),
        sa.Column("basis", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True), sa.Column("revoke_reason", sa.Text(), nullable=True))
    op.create_index("uq_intake_case_active", "intake_case_links", ["intake_id"], unique=True,
                    sqlite_where=sa.text("status = 'ACTIVE'"), postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_index("ix_intake_case_case_created", "intake_case_links", ["org_id", "case_id", "created_at", "id"])


def downgrade():
    op.drop_table("intake_case_links")
