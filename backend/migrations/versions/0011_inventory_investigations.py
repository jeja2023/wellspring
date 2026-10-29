"""Record investigation and review without changing evidence balances."""
from alembic import op
import sqlalchemy as sa
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("inventory_investigations",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("observation_id",sa.String(36),sa.ForeignKey("evidence_inventory_observations.id"),nullable=False),sa.Column("status",sa.String(30),nullable=False),sa.Column("investigator_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("last_submitter_id",sa.String(36),sa.ForeignKey("users.id"),nullable=True),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("observation_id",name="uq_inventory_investigation_observation"))
    for col in ("org_id","observation_id"):op.create_index("ix_inventory_investigations_"+col,"inventory_investigations",[col])
    op.create_table("inventory_investigation_events",sa.Column("id",sa.String(36),primary_key=True),sa.Column("org_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("investigation_id",sa.String(36),sa.ForeignKey("inventory_investigations.id"),nullable=False),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("action",sa.String(30),nullable=False),sa.Column("before_status",sa.String(30),nullable=True),sa.Column("after_status",sa.String(30),nullable=False),sa.Column("note",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    for col in ("org_id","investigation_id"):op.create_index("ix_inventory_investigation_events_"+col,"inventory_investigation_events",[col])

def downgrade():
    op.drop_table("inventory_investigation_events")
    op.drop_table("inventory_investigations")
