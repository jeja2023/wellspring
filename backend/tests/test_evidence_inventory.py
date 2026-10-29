from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.main import app
from wellspring.models import Evidence, EvidenceInventoryObservation, IdempotencyRecord, WeightEvent
from test_workflow import context, auth, headers


def setup_item(client, actor):
    case=client.post('/api/cases',headers=headers(actor),json={'number':'INV-1','title':'虚构案件'}).json()
    return client.post('/api/evidence',headers=headers(actor),json={'case_id':case['id'],'label':'虚构证物','weight':'83.000000','reason':'初称'}).json()


def test_inventory_preserves_balance_and_scope(context):
    client,factory=context
    a,b=auth(client,'alice'),auth(client,'bob')
    item=setup_item(client,a);url=f"/api/evidence/{item['id']}/inventory-observations"
    body={'evidence_version':1,'observed_weight':'82.900000','note':'虚构盘点'}
    assert client.post(url,json=body).status_code==401
    assert client.post(url,headers=headers(b),json=body).status_code==404
    assert client.get(url,headers=b).status_code==404
    same=headers(a);first=client.post(url,headers=same,json=body)
    assert first.status_code==201
    assert Decimal(first.json()['difference'])==Decimal('-0.100000')
    assert Decimal(first.json()['book_weight'])==Decimal('83')
    assert first.json()['actor_id'] and first.json()['evidence_version']==1 and first.json()['created_at'].endswith('+00:00')
    assert client.post(url,headers=same,json=body).json()==first.json()
    assert client.post(url,headers=same,json={**body,'note':'不同'}).json()['code']=='IDEMPOTENCY_CONFLICT'
    assert client.post(url,headers=headers(a),json=body).json()['code']=='VERSION_CONFLICT'
    assert client.post(url,headers=headers(a),json={**body,'evidence_version':2,'observed_weight':'-1'}).status_code==422
    assert client.post(url,headers=headers(a),json={**body,'evidence_version':2,'observed_weight':'0.0000001'}).status_code==422
    assert client.get(url,headers=a).json()['total']==1
    with factory() as db:
        evidence=db.get(Evidence,item['id'])
        assert evidence.balance==Decimal('83') and evidence.version==2
        assert len(db.scalars(select(WeightEvent)).all())==1
        assert len(db.scalars(select(EvidenceInventoryObservation)).all())==1
    # 盘点之后旧分样版本被拒绝，不会基于过期余额写入。
    assert client.post(f"/api/evidence/{item['id']}/samples",headers=headers(a),json={'source_version':1,'weight':'1','label':'样品','reason':'测试'}).status_code==409


def test_inventory_audit_failure_rolls_back(context):
    client,factory=context; a=auth(client,'alice'); item=setup_item(client,a)
    engine=factory.kw['bind']
    with engine.begin() as db:
        db.execute(text("CREATE TRIGGER fail_inventory_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'EVIDENCE_INVENTORY_CREATE' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    url=f"/api/evidence/{item['id']}/inventory-observations"; same=headers(a)
    body={'evidence_version':1,'observed_weight':'82.9','note':'测试'}
    with TestClient(app,raise_server_exceptions=False) as safe:
        assert safe.post(url,headers=same,json=body).status_code==500
    with engine.begin() as db: db.execute(text('DROP TRIGGER fail_inventory_audit'))
    with factory() as db:
        assert db.get(Evidence,item['id']).version==1
        assert db.scalars(select(EvidenceInventoryObservation)).all()==[]
        assert db.scalars(select(IdempotencyRecord).where(IdempotencyRecord.operation=='EVIDENCE_INVENTORY_CREATE')).all()==[]
    assert client.post(url,headers=same,json=body).status_code==201
