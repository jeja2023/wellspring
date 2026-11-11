"""Development case-information baseline."""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    optional = ("alarm_type", "receiving_unit", "receiving_branch", "alarm_content", "alarm_address", "caller", "alarm_time", "caller_phone", "additional_result", "feedback_time", "modification_time", "standardized_address", "brief_result", "category", "result", "involved_items", "apprehended_people", "tags", "note")
    op.create_table(
        "case_information",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("number", sa.String(80), nullable=False, unique=True),
        *(sa.Column(name, sa.Text(), nullable=True) for name in optional),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_case_information_org_id", "case_information", ["org_id"])


def downgrade():
    op.drop_index("ix_case_information_org_id", table_name="case_information")
    op.drop_table("case_information")
