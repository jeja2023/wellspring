"""Removal regression: old schemas upgrade cleanly, current routes and grants stay absent."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from sqlalchemy import inspect
from wellspring.main import app
from wellspring.db import Base
from wellspring.access_policy import CODES
from test_workflow import context,auth

REMOVED={'evidence','weight_events','evidence_inventory_observations','inventory_investigations','inventory_investigation_events','evidence_custody','custody_handovers','custody_events'}


def test_current_metadata_permissions_routes_and_source_files_are_removed(context):
    client,factory=context
    assert not REMOVED & set(Base.metadata.tables)
    assert not any(code.startswith('evidence.') for code in CODES)
    assert not any(path.startswith('/api/evidence') for path in app.openapi()['paths'])
    for path in ['/api/evidence','/api/evidence/old/events','/api/evidence/old/samples']:
        assert client.get(path,headers=auth(client,'alice')).status_code==404
    root=Path(__file__).resolve().parents[2]
    for name in ['backend/wellspring/evidence_inventory.py','backend/wellspring/evidence_custody.py','backend/wellspring/inventory_investigations.py','frontend/src/features/evidence']:
        assert not (root/name).exists()


def test_explicit_cleanup_migration_drops_old_tables_and_preserves_other_data(tmp_path):
    root=Path(__file__).resolve().parents[2];backend=root/'backend';database=tmp_path/'old.db'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+database.as_posix(),'PYTHONUTF8':'1'}
    def run(*args):
        result=subprocess.run([sys.executable,*args],cwd=backend,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
        assert result.returncode==0,result.stdout+result.stderr
    run('-m','alembic','upgrade','0025')
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO organizations(id,name,unit_type,active,version) VALUES ('org','合成保留组织','CITY',1,1)")
        db.execute("INSERT INTO cases(id,org_id,number,title,status,created_at) VALUES ('case','org','KEEP','合成保留案件','DRAFT','2026-11-11')")
        db.create_function('wellspring_decimal_valid',1,lambda _:1)
        db.create_function('wellspring_decimal_compare',2,lambda a,b:1)
        db.execute("INSERT INTO evidence(id,org_id,case_id,parent_id,label,balance,version,created_at) VALUES ('old','org','case',NULL,'待清除','1.000000',1,'2026-11-11')")
    # Unsafe data removal must be refused by automatic startup.
    run('-c',"from wellspring.startup_migrations import upgrade,MigrationRefused; import os;\ntry: upgrade(os.environ['DATABASE_URL'])\nexcept MigrationRefused: pass\nelse: raise AssertionError('automatic deletion must be refused')")
    run('-c',"from wellspring.startup_migrations import upgrade; import os; from pathlib import Path; upgrade(os.environ['DATABASE_URL'],automatic=False,backup_dir=Path(r'"+str(tmp_path/'backups')+"'))")
    run('-m','alembic','check')
    with sqlite3.connect(database) as db:
        tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not tables&REMOVED
        assert db.execute("SELECT title FROM cases WHERE id='case'").fetchone()[0]=='合成保留案件'
        assert not any(code.startswith('evidence.') for code in json.loads(db.execute("SELECT permissions_json FROM roles WHERE id='wellspring-business-user'").fetchone()[0]))
    assert list((tmp_path/'backups').glob('*.sqlite3'))
