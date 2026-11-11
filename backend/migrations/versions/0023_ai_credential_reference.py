"""Reference a server-only credential without storing plaintext keys in the database."""
from alembic import op
import sqlalchemy as sa
revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None
startup_safe = True


def upgrade():
    op.add_column("ai_services", sa.Column("api_key_ref", sa.String(36), nullable=True))


def downgrade():
    with op.batch_alter_table("ai_services") as batch:
        batch.drop_column("api_key_ref")
