"""Preserve unverified people and add scoped records, legal episodes and transfers."""
from alembic import op
import sqlalchemy as sa
revision='0027'
down_revision='0026'
branch_labels=None
depends_on=None
startup_safe=True


def upgrade():
    with op.batch_alter_table('person_drafts') as batch:
        for name,length in [('document_type',30),('document_number',100)]:batch.add_column(sa.Column(name,sa.String(length),nullable=True))
        batch.add_column(sa.Column('birth_date',sa.Date(),nullable=True))
        batch.add_column(sa.Column('phone',sa.String(100),server_default='',nullable=False))
        batch.add_column(sa.Column('address',sa.Text(),server_default='',nullable=False))
        for name,table in [('responsible_org_id','organizations'),('responsible_user_id','users'),('verified_by','users'),('updated_by','users')]:
            batch.add_column(sa.Column(name,sa.String(36),nullable=True));batch.create_foreign_key('fk_person_'+name,table,[name],['id'])
        batch.add_column(sa.Column('verified_at',sa.DateTime(timezone=True),nullable=True))
    def identity(name,table):return sa.Column(name,sa.String(36),sa.ForeignKey(table+'.id'),nullable=False)
    op.create_table('person_records',sa.Column('id',sa.String(36),primary_key=True),identity('person_id','person_drafts'),identity('org_id','organizations'),identity('manager_org_id','organizations'),
        sa.Column('kind',sa.String(30),nullable=False),sa.Column('record_type',sa.String(40),nullable=False),sa.Column('occurred_on',sa.Date(),nullable=False),
        sa.Column('source',sa.String(200),nullable=False),sa.Column('document_no',sa.String(200),nullable=False),sa.Column('basis',sa.Text(),nullable=False),sa.Column('details_json',sa.Text(),nullable=False),
        sa.Column('case_id',sa.String(36),sa.ForeignKey('cases.id'),nullable=True),sa.Column('replaces_id',sa.String(36),sa.ForeignKey('person_records.id'),nullable=True),
        sa.Column('verification_status',sa.String(20),nullable=False),sa.Column('state',sa.String(30),nullable=False),
        sa.Column('expected_end_on',sa.Date(),nullable=True),sa.Column('actual_start_on',sa.Date(),nullable=True),sa.Column('actual_end_on',sa.Date(),nullable=True),
        identity('created_by','users'),sa.Column('updated_by',sa.String(36),sa.ForeignKey('users.id'),nullable=True),sa.Column('verified_by',sa.String(36),sa.ForeignKey('users.id'),nullable=True),sa.Column('verified_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_person_record_scope_kind','person_records',['person_id','org_id','kind','verification_status','created_at','id'])
    op.create_table('person_events',sa.Column('id',sa.String(36),primary_key=True),identity('person_id','person_drafts'),
        sa.Column('record_id',sa.String(36),sa.ForeignKey('person_records.id'),nullable=True),identity('org_id','organizations'),identity('actor_id','users'),
        sa.Column('action',sa.String(40),nullable=False),sa.Column('note',sa.Text(),nullable=False),sa.Column('payload_json',sa.Text(),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_person_event_created','person_events',['person_id','created_at','id'])
    op.create_table('person_tasks',sa.Column('id',sa.String(36),primary_key=True),identity('person_id','person_drafts'),
        sa.Column('record_id',sa.String(36),sa.ForeignKey('person_records.id'),nullable=True),identity('org_id','organizations'),
        sa.Column('task_type',sa.String(30),nullable=False),sa.Column('title',sa.String(200),nullable=False),sa.Column('due_on',sa.Date(),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('result_note',sa.Text(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),identity('created_by','users'),
        sa.Column('completed_by',sa.String(36),sa.ForeignKey('users.id'),nullable=True),sa.Column('completed_at',sa.DateTime(timezone=True),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_person_task_org_due','person_tasks',['org_id','status','due_on','id'])
    op.create_table('person_transfers',sa.Column('id',sa.String(36),primary_key=True),identity('person_id','person_drafts'),identity('source_org_id','organizations'),identity('target_org_id','organizations'),
        identity('requested_by','users'),sa.Column('accepted_by',sa.String(36),sa.ForeignKey('users.id'),nullable=True),sa.Column('reason',sa.Text(),nullable=False),sa.Column('response_note',sa.Text(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('completed_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_person_transfer_target','person_transfers',['target_org_id','status','created_at','id'])
    op.create_index('uq_person_transfer_pending','person_transfers',['person_id'],unique=True,sqlite_where=sa.text("status='PENDING'"),postgresql_where=sa.text("status='PENDING'"))


def downgrade():
    raise RuntimeError('人员业务记录及措施历史需保留，请使用完整匹配备份恢复。')
