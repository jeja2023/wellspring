"""Stage and reconcile development-only case imports."""
from alembic import op
import sqlalchemy as sa
revision="0012"
down_revision="0011"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("case_import_batches",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("source",sa.String(200),nullable=False),sa.Column("digest",sa.String(64),nullable=False),sa.Column("mapping_version",sa.String(30),nullable=False),sa.Column("status",sa.String(30),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("completed_at",sa.DateTime(timezone=True),nullable=True))
    for col in ("org_id","actor_id"):op.create_index("ix_case_import_batches_"+col,"case_import_batches",[col])
    op.create_table("case_import_rows",sa.Column("id",sa.String(36),primary_key=True),sa.Column("batch_id",sa.String(36),sa.ForeignKey("case_import_batches.id"),nullable=False),sa.Column("line_number",sa.Integer(),nullable=False),sa.Column("number",sa.String(80),nullable=False),sa.Column("title",sa.String(200),nullable=False),sa.Column("preview_status",sa.String(30),nullable=False),sa.Column("result_status",sa.String(30),nullable=True),sa.Column("reason",sa.Text(),nullable=False),sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=True),sa.UniqueConstraint("batch_id","line_number",name="uq_case_import_batch_line"))
    op.create_index("ix_case_import_rows_batch_id","case_import_rows",["batch_id"])

def downgrade():
    op.drop_table("case_import_rows")
    op.drop_table("case_import_batches")
