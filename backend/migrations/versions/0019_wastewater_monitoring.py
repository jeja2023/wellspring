"""Independent wastewater sites, samples, lab observations and review history."""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None
startup_safe = True  # Additive independent tables; no existing rows are rewritten.


def upgrade():
    decimal = sa.Numeric(20, 6).with_variant(sa.Text(), "sqlite")
    op.create_table("wastewater_sites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("district", sa.String(200), nullable=False), sa.Column("plant_name", sa.String(200), nullable=False),
        sa.Column("catchment", sa.Text(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("state_note", sa.Text(), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "code", name="uq_wastewater_site_org_code"))
    op.create_index("ix_wastewater_site_org_created", "wastewater_sites", ["org_id", "created_at", "id"])
    op.create_table("wastewater_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("wastewater_sites.id"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False), sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sampling_method", sa.String(30), nullable=False), sa.Column("collector", sa.String(100), nullable=False),
        sa.Column("flow_m3_day", decimal, nullable=True), sa.Column("quality", sa.String(30), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "code", name="uq_wastewater_sample_org_code"))
    op.create_index("ix_wastewater_sample_org_site_time", "wastewater_samples", ["org_id", "site_id", "sampled_at", "id"])
    op.create_table("wastewater_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("sample_id", sa.String(36), sa.ForeignKey("wastewater_samples.id"), nullable=False),
        sa.Column("analyte", sa.String(120), nullable=False), sa.Column("detection", sa.String(30), nullable=False),
        sa.Column("concentration", decimal, nullable=True), sa.Column("quantification_limit", decimal, nullable=True),
        sa.Column("laboratory", sa.String(200), nullable=False), sa.Column("analysis_method", sa.String(200), nullable=False),
        sa.Column("report_number", sa.String(100), nullable=False), sa.Column("note", sa.Text(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sample_id", "analyte", "laboratory", "report_number", name="uq_wastewater_result_report"))
    op.create_index("ix_wastewater_result_org_state_created", "wastewater_results", ["org_id", "state", "created_at", "id"])
    op.create_table("wastewater_result_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("result_id", sa.String(36), sa.ForeignKey("wastewater_results.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False), sa.Column("note", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_wastewater_event_result_created", "wastewater_result_events", ["result_id", "created_at", "id"])


def downgrade():
    for table in ("wastewater_result_events", "wastewater_results", "wastewater_samples", "wastewater_sites"):
        op.drop_table(table)
