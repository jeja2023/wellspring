"""Modeling, business models and tactics with scoped versioned records."""
import json
from alembic import op
import sqlalchemy as sa
revision='0025'
down_revision='0024'
branch_labels=None
depends_on=None
startup_safe=True


def upgrade():
    op.create_table('analysis_assets',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('org_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('kind',sa.String(20),nullable=False),sa.Column('code',sa.String(80),nullable=False),sa.Column('name',sa.String(200),nullable=False),
        sa.Column('category',sa.String(30),nullable=False),sa.Column('description',sa.Text(),nullable=False),sa.Column('config_json',sa.Text(),nullable=False),
        sa.Column('project_id',sa.String(36),sa.ForeignKey('analysis_assets.id'),nullable=True),sa.Column('model_id',sa.String(36),sa.ForeignKey('analysis_assets.id'),nullable=True),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_by',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('updated_by',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('org_id','kind','code',name='uq_analysis_asset_org_kind_code'))
    op.create_index('ix_analysis_asset_org_kind_created','analysis_assets',['org_id','kind','created_at','id'])
    op.create_table('analysis_asset_events',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('asset_id',sa.String(36),sa.ForeignKey('analysis_assets.id'),nullable=False),sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('org_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),sa.Column('action',sa.String(30),nullable=False),
        sa.Column('note',sa.Text(),nullable=False),sa.Column('snapshot_json',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_analysis_asset_event_created','analysis_asset_events',['asset_id','created_at','id'])
    connection=op.get_bind();raw=connection.scalar(sa.text('SELECT permissions_json FROM roles WHERE id=:id'),{'id':'wellspring-business-user'})
    if raw:
        permissions=set(json.loads(raw))|{prefix+'.'+action for prefix in ['modeling','models','tactics'] for action in ['read','write']}
        connection.execute(sa.text('UPDATE roles SET permissions_json=:permissions,version=version+1 WHERE id=:id'),{'permissions':json.dumps(sorted(permissions)),'id':'wellspring-business-user'})


def downgrade():
    raise RuntimeError('建模、模型和技战法包含版本历史，请通过已验证备份恢复，禁止有损降级。')
