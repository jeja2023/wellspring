"""Add an optional user-specified investigation due date."""
from alembic import op
import sqlalchemy as sa
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("investigation_tasks", sa.Column("due_date", sa.Date(), nullable=True))

def downgrade():
    op.drop_column("investigation_tasks", "due_date")
