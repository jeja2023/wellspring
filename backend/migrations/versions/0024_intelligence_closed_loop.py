"""Hierarchical clue deliveries, controlled Excel intake and feedback history."""
import json
from alembic import op
import sqlalchemy as sa
revision="0024"
down_revision="0023"
branch_labels=None
depends_on=None
startup_safe=True


def upgrade():
    op.add_column('organizations',sa.Column('unit_type',sa.String(20),server_default='OTHER',nullable=False))
    op.create_table('clue_import_batches',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('org_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('filename',sa.String(200),nullable=False),
        sa.Column('content_sha256',sa.String(64),nullable=False),sa.Column('total',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_clue_import_org_created','clue_import_batches',['org_id','created_at','id'])
    with op.batch_alter_table('clues') as batch:
        batch.add_column(sa.Column('reference_no',sa.String(80),nullable=True))
        batch.add_column(sa.Column('priority',sa.String(20),server_default='NORMAL',nullable=False))
        batch.add_column(sa.Column('suggested_due_date',sa.Date(),nullable=True))
        batch.add_column(sa.Column('import_batch_id',sa.String(36),nullable=True))
        batch.create_foreign_key('fk_clue_import_batch','clue_import_batches',['import_batch_id'],['id'])
    op.create_index('uq_clue_org_reference','clues',['org_id','reference_no'],unique=True)
    op.add_column('intelligence_events',sa.Column('payload_json',sa.Text(),nullable=True))
    op.create_table('clue_deliveries',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('clue_id',sa.String(36),sa.ForeignKey('clues.id'),nullable=False),
        sa.Column('parent_id',sa.String(36),sa.ForeignKey('clue_deliveries.id'),nullable=True),
        sa.Column('sender_org_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('recipient_org_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('sender_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('assignee_id',sa.String(36),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('objective',sa.Text(),nullable=False),sa.Column('due_date',sa.Date(),nullable=True),
        sa.Column('allow_station',sa.Boolean(),nullable=False),sa.Column('snapshot_json',sa.Text(),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),sa.Column('disposition_text',sa.Text(),nullable=False),
        sa.Column('feedback_text',sa.Text(),nullable=False),sa.Column('result_code',sa.String(30),nullable=True),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('accepted_at',sa.DateTime(timezone=True),nullable=True),sa.Column('feedback_at',sa.DateTime(timezone=True),nullable=True),sa.Column('closed_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_delivery_recipient_status','clue_deliveries',['recipient_org_id','status','created_at','id'])
    op.create_index('ix_delivery_sender_created','clue_deliveries',['sender_org_id','created_at','id'])
    op.create_index('ix_delivery_parent','clue_deliveries',['parent_id'])
    op.create_index('uq_delivery_active_destination','clue_deliveries',['clue_id','recipient_org_id'],unique=True,
        sqlite_where=sa.text("status != 'CLOSED'"),postgresql_where=sa.text("status != 'CLOSED'"))
    op.create_table('clue_delivery_events',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('delivery_id',sa.String(36),sa.ForeignKey('clue_deliveries.id'),nullable=False),
        sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('actor_org_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('action',sa.String(30),nullable=False),sa.Column('note',sa.Text(),nullable=False),
        sa.Column('before_status',sa.String(30),nullable=True),sa.Column('after_status',sa.String(30),nullable=False),
        sa.Column('payload_json',sa.Text(),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_delivery_event_created','clue_delivery_events',['delivery_id','created_at','id'])
    connection=op.get_bind()
    raw=connection.scalar(sa.text('SELECT permissions_json FROM roles WHERE id=:id'),{'id':'wellspring-business-user'})
    if raw:
        permissions=set(json.loads(raw))|{'intelligence.import','intelligence.dispatch','intelligence.dispose','intelligence.review'}
        connection.execute(sa.text('UPDATE roles SET permissions_json=:permissions,version=version+1 WHERE id=:id'),{'permissions':json.dumps(sorted(permissions)),'id':'wellspring-business-user'})


def downgrade():
    raise RuntimeError('线索下发及反馈历史需要保留，请使用已验证备份恢复，不提供丢失闭环数据的降级。')
