"""Development intelligence workflow tables."""
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("clues", sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("title",sa.String(200),nullable=False),sa.Column("summary",sa.Text(),nullable=False),sa.Column("source",sa.String(200),nullable=False),sa.Column("status",sa.String(30),nullable=False),sa.Column("created_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_clues_org_id","clues",["org_id"])
    op.create_table("investigation_tasks",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("clue_id",sa.String(36),sa.ForeignKey("clues.id"),nullable=False),sa.Column("objective",sa.Text(),nullable=False),sa.Column("assignee_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("status",sa.String(30),nullable=False),sa.Column("last_submitter_id",sa.String(36),sa.ForeignKey("users.id"),nullable=True),sa.Column("result_code",sa.String(30),nullable=True),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("clue_id",name="uq_investigation_task_clue"))
    op.create_index("ix_investigation_tasks_org_id","investigation_tasks",["org_id"])
    op.create_index("ix_investigation_tasks_clue_id","investigation_tasks",["clue_id"])
    op.create_table("intelligence_events",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("clue_id",sa.String(36),sa.ForeignKey("clues.id"),nullable=False),sa.Column("task_id",sa.String(36),sa.ForeignKey("investigation_tasks.id"),nullable=True),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("action",sa.String(40),nullable=False),sa.Column("before_status",sa.String(30),nullable=True),sa.Column("after_status",sa.String(30),nullable=False),sa.Column("note",sa.Text(),nullable=False),sa.Column("result_code",sa.String(30),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    for column in ("org_id","clue_id","task_id"): op.create_index("ix_intelligence_events_"+column,"intelligence_events",[column])

def downgrade():
    op.drop_table("intelligence_events")
    op.drop_table("investigation_tasks")
    op.drop_table("clues")
