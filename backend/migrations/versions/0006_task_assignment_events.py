"""Record before/after assignees in append-only workflow events."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("intelligence_events", sa.Column("assignee_before_id", sa.String(36), nullable=True))
    op.add_column("intelligence_events", sa.Column("assignee_after_id", sa.String(36), nullable=True))

def downgrade():
    op.drop_column("intelligence_events", "assignee_after_id")
    op.drop_column("intelligence_events", "assignee_before_id")
