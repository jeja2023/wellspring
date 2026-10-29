"""Add unverified person-to-case candidate links."""
from alembic import op
import sqlalchemy as sa
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("person_case_candidates",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("person_id",sa.String(36),sa.ForeignKey("person_drafts.id"),nullable=False),sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),sa.Column("basis",sa.Text(),nullable=False),sa.Column("status",sa.String(20),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("revoked_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),sa.Column("revoked_at",sa.DateTime(timezone=True),nullable=True),sa.Column("revoke_reason",sa.Text(),nullable=True))
    for col in ("org_id","person_id","case_id"):op.create_index("ix_person_case_candidates_"+col,"person_case_candidates",[col])
    op.create_index("uq_person_case_candidate_active","person_case_candidates",["person_id","case_id"],unique=True,sqlite_where=sa.text("status = 'ACTIVE'"),postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_table("person_case_candidate_events",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("candidate_id",sa.String(36),sa.ForeignKey("person_case_candidates.id"),nullable=False),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("action",sa.String(30),nullable=False),sa.Column("note",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    for col in ("org_id","candidate_id"):op.create_index("ix_person_case_candidate_events_"+col,"person_case_candidate_events",[col])

def downgrade():
    op.drop_table("person_case_candidate_events")
    op.drop_table("person_case_candidates")
