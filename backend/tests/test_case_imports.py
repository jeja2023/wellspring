from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.main import app
from wellspring.models import Case, CaseImportBatch, CaseImportRow, Organization, User
from wellspring.security import password_hash
from test_workflow import context, auth, headers


def test_stage_confirm_conflicts_and_provenance(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob')
    with factory() as db:
        org=db.scalar(select(Organization).where(Organization.name=='A'))
        db.add(User(username='peer',org_id=org.id,password_hash=password_hash('test-password-123')));db.commit()
    peer=auth(client,'peer')
    client.post('/api/cases',headers=headers(a),json={'number':'EXIST','title':'原有'})
    content='案件编号,案件名称\nNEW,新建\nEXIST,不覆盖\nLATE,并发\nNEW,重复\n,缺编号'
    payload={'source':'虚构来源','content':content};key=headers(a)
    assert client.post('/api/imports/case-batches',json=payload).status_code==401
    stage=client.post('/api/imports/case-batches',headers=key,json=payload);assert stage.status_code==201
    batch=stage.json();bid=batch['id']
    assert client.post('/api/imports/case-batches',headers=key,json=payload).json()==batch
    assert client.get(f'/api/imports/case-batches/{bid}',headers=b).status_code==404
    assert client.get(f'/api/imports/case-batches/{bid}',headers=peer).status_code==404
    rows=client.get(f'/api/imports/case-batches/{bid}?page_size=20',headers=a).json()['rows']['items']
    assert [r['preview_status'] for r in rows]==['NEW','CONFLICT','NEW','ERROR','ERROR']
    client.post('/api/cases',headers=headers(a),json={'number':'LATE','title':'预览后创建'})
    ck=headers(a);result=client.post(f'/api/imports/case-batches/{bid}/confirm',headers=ck,json={})
    assert result.status_code==200 and result.json()['counts']=={'created':1,'conflict':2,'error':2}
    assert client.post(f'/api/imports/case-batches/{bid}/confirm',headers=ck,json={}).json()==result.json()
    assert client.post(f'/api/imports/case-batches/{bid}/confirm',headers=headers(a),json={}).status_code==409
    detail=client.get(f'/api/imports/case-batches/{bid}',headers=a).json()
    rows=detail['rows']['items'];assert [r['result_status'] for r in rows]==['CREATED','CONFLICT','CONFLICT','ERROR','ERROR']
    assert rows[0]['case_id'] and detail['batch']['source']=='虚构来源' and detail['batch']['sha256']==batch['sha256']
    with factory() as db:
        cases=db.scalars(select(Case).order_by(Case.number)).all()
        assert {c.number:c.title for c in cases}=={'EXIST':'原有','LATE':'预览后创建','NEW':'新建'}
        assert db.scalars(select(CaseImportRow).where(CaseImportRow.case_id.is_not(None))).one().case_id==rows[0]['case_id']


def test_audit_failure_rolls_back_all_and_retry(context):
    client,factory=context;a=auth(client,'alice')
    stage=client.post('/api/imports/case-batches',headers=headers(a),json={'source':'虚构','content':'案件编号,案件名称\nA-1,示例\nA-2,示例'})
    bid=stage.json()['id'];route=f'/api/imports/case-batches/{bid}/confirm';key=headers(a);engine=factory.kw['bind']
    with engine.begin() as db:db.execute(text("CREATE TRIGGER fail_import_audit BEFORE INSERT ON audit_events WHEN NEW.action='CASE_IMPORT_CONFIRM' BEGIN SELECT RAISE(ABORT,'audit unavailable'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe:assert safe.post(route,headers=key,json={}).status_code==500
    with engine.begin() as db:db.execute(text('DROP TRIGGER fail_import_audit'))
    with factory() as db:
        assert db.scalars(select(Case)).all()==[]
        assert db.get(CaseImportBatch,bid).status=='PREVIEW'
        assert all(row.result_status is None for row in db.scalars(select(CaseImportRow).where(CaseImportRow.batch_id==bid)).all())
    assert client.post(route,headers=key,json={}).json()['counts']['created']==2


def test_cancel_is_idempotent_and_preserves_staged_data(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob')
    batch=client.post('/api/imports/case-batches',headers=headers(a),json={'source':'虚构','content':'案件编号,案件名称\nA-1,示例'}).json()
    bid=batch['id'];url=f'/api/imports/case-batches/{bid}/cancel';key=headers(a)
    assert client.post(url,headers=headers(b),json={}).status_code==404
    assert client.post(url,headers=key,json={}).json()['status']=='CANCELLED'
    assert client.post(url,headers=key,json={}).status_code==200
    assert client.post(f'/api/imports/case-batches/{bid}/confirm',headers=headers(a),json={}).status_code==409
    detail=client.get(f'/api/imports/case-batches/{bid}',headers=a).json()
    assert detail['batch']['status']=='CANCELLED' and detail['rows']['total']==1
    with factory() as db:assert db.scalars(select(Case)).all()==[]
