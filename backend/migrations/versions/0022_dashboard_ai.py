"""Scoped dashboard access and configurable AI-generated drafts."""
import json
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None
startup_safe = True


def upgrade():
    op.create_table("ai_services",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("base_url", sa.String(1000), nullable=False), sa.Column("model", sa.String(200), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False), sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("token_parameter", sa.String(30), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("check_ok", sa.Boolean()), sa.Column("check_message", sa.String(300), nullable=False))
    service = sa.table("ai_services", sa.column("id"), sa.column("enabled", sa.Boolean()), sa.column("base_url"), sa.column("model"),
        sa.column("timeout_seconds", sa.Integer()), sa.column("max_output_tokens", sa.Integer()), sa.column("token_parameter"),
        sa.column("version", sa.Integer()), sa.column("updated_at", sa.DateTime(timezone=True)), sa.column("check_message"))
    op.bulk_insert(service, [dict(id="primary", enabled=False, base_url="", model="", timeout_seconds=60,
        max_output_tokens=2048, token_parameter="max_tokens", version=1, updated_at=datetime.now(timezone.utc), check_message="")])
    op.create_table("ai_runs",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("model", sa.String(200), nullable=False),
        sa.Column("service_version", sa.Integer(), nullable=False), sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("input_chars", sa.Integer(), nullable=False), sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(60), nullable=False), sa.Column("error_message", sa.String(300), nullable=False),
        sa.Column("prompt_tokens", sa.Integer()), sa.Column("completion_tokens", sa.Integer()),
        sa.Column("truncated", sa.Boolean(), nullable=False), sa.Column("duration_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_ai_run_owner_created", "ai_runs", ["org_id", "actor_id", "created_at", "id"])
    op.create_index("uq_ai_run_active_actor", "ai_runs", ["actor_id"], unique=True,
        sqlite_where=sa.text("status IN ('QUEUED','RUNNING')"), postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"))
    connection = op.get_bind()
    raw = connection.scalar(sa.text("SELECT permissions_json FROM roles WHERE id=:id"), {"id": "wellspring-business-user"})
    if raw is not None:
        permissions = set(json.loads(raw)) | {"dashboard.read", "ai.read"}
        connection.execute(sa.text("UPDATE roles SET permissions_json=:permissions, version=version+1 WHERE id=:id"),
            {"permissions": json.dumps(sorted(permissions)), "id": "wellspring-business-user"})


def downgrade():
    connection = op.get_bind()
    rows = list(connection.execute(sa.text("SELECT id, permissions_json FROM roles")))
    for identity, raw in rows:
        permissions = [code for code in json.loads(raw) if code not in {"dashboard.read", "ai.read", "ai.generate", "system.ai"}]
        connection.execute(sa.text("UPDATE roles SET permissions_json=:permissions WHERE id=:id"),
            {"permissions": json.dumps(permissions), "id": identity})
    op.drop_table("ai_runs")
    op.drop_table("ai_services")
