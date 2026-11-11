"""Add places and manually sourced nonpersonal map locations."""
from alembic import op
import sqlalchemy as sa

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None
startup_safe = True


def upgrade():
    def identity(name, table, nullable=False):
        return sa.Column(name, sa.String(36), sa.ForeignKey(table + '.id'), nullable=nullable)
    def primary():
        return sa.Column('id', sa.String(36), primary_key=True)
    def created():
        return [identity('created_by', 'users'), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False)]
    op.create_table('places', primary(), identity('org_id', 'organizations'),
        sa.Column('code', sa.String(80), nullable=False), sa.Column('name', sa.String(200), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False), sa.Column('district', sa.String(200), nullable=False),
        sa.Column('address', sa.String(500), nullable=False), sa.Column('responsible', sa.String(100), nullable=False),
        sa.Column('management_basis', sa.Text(), nullable=False), sa.Column('review_on', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False), sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False), *created(),
        sa.UniqueConstraint('org_id', 'code', name='uq_place_org_code'))
    op.create_index('ix_place_org_updated', 'places', ['org_id', 'updated_at', 'id'])
    op.create_table('place_inspections', primary(), identity('org_id', 'organizations'), identity('place_id', 'places'),
        sa.Column('inspected_on', sa.Date(), nullable=False), sa.Column('findings', sa.Text(), nullable=False),
        sa.Column('due_on', sa.Date(), nullable=True), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('result_note', sa.Text(), nullable=False), identity('completed_by', 'users', True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True), sa.Column('version', sa.Integer(), nullable=False), *created())
    op.create_index('ix_place_inspection_scope', 'place_inspections', ['org_id', 'place_id', 'created_at', 'id'])
    op.create_table('place_incidents', primary(), identity('org_id', 'organizations'), identity('place_id', 'places'),
        sa.Column('title', sa.String(200), nullable=False), sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(200), nullable=False), sa.Column('facts', sa.Text(), nullable=False),
        sa.Column('material_ref', sa.String(500), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('disposition', sa.Text(), nullable=False), identity('last_editor_id', 'users'), identity('submitted_by', 'users', True),
        identity('clue_id', 'clues', True), sa.Column('version', sa.Integer(), nullable=False), *created())
    op.create_index('ix_place_incident_scope', 'place_incidents', ['org_id', 'place_id', 'created_at', 'id'])
    op.create_table('place_events', primary(), identity('org_id', 'organizations'), identity('place_id', 'places'),
        sa.Column('resource_id', sa.String(36), nullable=False), identity('actor_id', 'users'),
        sa.Column('action', sa.String(40), nullable=False), sa.Column('note', sa.Text(), nullable=False),
        sa.Column('snapshot_json', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_place_event_created', 'place_events', ['place_id', 'created_at', 'id'])
    op.create_table('geo_locations', primary(), identity('org_id', 'organizations'),
        sa.Column('resource_type', sa.String(20), nullable=False), sa.Column('resource_id', sa.String(36), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=True), sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('source', sa.String(500), nullable=False), sa.Column('version', sa.Integer(), nullable=False),
        identity('updated_by', 'users'), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('resource_type', 'resource_id', name='uq_geo_resource'),
        sa.CheckConstraint('(longitude IS NULL AND latitude IS NULL) OR (longitude IS NOT NULL AND latitude IS NOT NULL AND longitude >= -180 AND longitude <= 180 AND latitude >= -85 AND latitude <= 85)', name='ck_geo_coordinates'))
    op.create_index('ix_geo_org_type', 'geo_locations', ['org_id', 'resource_type'])
    op.create_table('geo_location_events', primary(), identity('location_id', 'geo_locations'), identity('org_id', 'organizations'),
        identity('actor_id', 'users'), sa.Column('snapshot_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_geo_event_created', 'geo_location_events', ['location_id', 'created_at', 'id'])


def downgrade():
    raise RuntimeError('场所事件、巡查和坐标历史应保留，请恢复匹配备份。')
