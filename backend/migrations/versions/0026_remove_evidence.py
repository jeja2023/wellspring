"""Permanently remove the evidence module, tables and stored grants."""
import json
from alembic import op
import sqlalchemy as sa
revision='0026'
down_revision='0025'
branch_labels=None
depends_on=None
# Data removal requires the explicit migration entry point and its prior backup.
startup_safe=False

TABLES=['custody_events','custody_handovers','evidence_custody','inventory_investigation_events',
        'inventory_investigations','evidence_inventory_observations','weight_events','evidence']


def upgrade():
    for table in TABLES:op.drop_table(table)
    connection=op.get_bind()
    for identity,raw in list(connection.execute(sa.text('SELECT id,permissions_json FROM roles'))):
        previous=json.loads(raw);permissions=[code for code in previous if not code.startswith('evidence.')]
        if permissions!=previous:
            connection.execute(sa.text('UPDATE roles SET permissions_json=:permissions,version=version+1 WHERE id=:id'),{'permissions':json.dumps(permissions),'id':identity})


def downgrade():
    raise RuntimeError('证物模块已按要求彻底移除，不能从空结构恢复历史数据；请恢复匹配的完整备份。')
