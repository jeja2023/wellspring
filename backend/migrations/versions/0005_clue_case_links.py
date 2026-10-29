"""Add traceable development clue-to-case links."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("intelligence_events", sa.Column("related_link_id", sa.String(36), nullable=True))
    op.create_index("ix_intelligence_events_related_link_id", "intelligence_events", ["related_link_id"])
    op.create_table(
        "clue_case_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("clue_id", sa.String(36), sa.ForeignKey("clues.id"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("revoked_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
    )
    for col in ("org_id", "clue_id", "case_id"):
        op.create_index("ix_clue_case_links_" + col, "clue_case_links", [col])
    op.create_index("uq_clue_case_active", "clue_case_links", ["clue_id", "case_id"], unique=True,
                    sqlite_where=sa.text("status = 'ACTIVE'"), postgresql_where=sa.text("status = 'ACTIVE'"))

def downgrade():
    op.drop_table("clue_case_links")
    op.drop_index("ix_intelligence_events_related_link_id", table_name="intelligence_events")
    op.drop_column("intelligence_events", "related_link_id")
