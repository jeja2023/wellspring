"""Indexes for scoped lists, audit history, sessions and task queues."""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None
startup_safe = True  # Local startup only: additive indexes, no data rewrite.

INDEXES = (
    ("ix_cases_org_created", "cases", ["org_id", "created_at", "id"]),
    ("ix_evidence_org_created", "evidence", ["org_id", "created_at", "id"]),
    ("ix_clues_org_created", "clues", ["org_id", "created_at", "id"]),
    ("ix_people_org_created", "person_drafts", ["org_id", "created_at", "id"]),
    ("ix_case_information_org_active_created", "case_information", ["org_id", "deleted_at", "created_at", "id"]),
    ("ix_case_information_active_created", "case_information", ["deleted_at", "created_at", "id"]),
    ("ix_audit_actor_created", "audit_events", ["actor_id", "created_at", "id"]),
    ("ix_audit_created", "audit_events", ["created_at", "id"]),
    ("ix_sessions_user_id", "sessions", ["user_id"]),
    ("ix_sessions_expires_at", "sessions", ["expires_at"]),
    ("ix_tasks_org_assignee_status", "investigation_tasks", ["org_id", "assignee_id", "status", "due_date", "id"]),
    ("ix_tasks_org_review_created", "investigation_tasks", ["org_id", "status", "created_at", "id"]),
)


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
