from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.main import app
from wellspring.models import Evidence, InventoryInvestigation, InventoryInvestigationEvent, Organization, User, WeightEvent
from wellspring.security import password_hash
from test_workflow import context,auth,headers
from test_evidence_inventory import setup_item


def test_investigation_review_is_separate_and_does_not_adjust_balance(context):
    client,factory=context
    with factory() as db:
        alice=db.scalar(select(User).where(User.username=='alice'))
        db.add(User(username='reviewer',org_id=alice.org_id,password_hash=password_hash('test-password-123')));db.commit()
    a,r,b=auth(client,'alice'),auth(client,'reviewer'),auth(client,'bob')
    item=setup_item(client,a)
    observation=client.post(f"/api/evidence/{item['id']}/inventory-observations",headers=headers(a),json={'evidence_version':1,'observed_weight':'82.9','note':'虚构盘点'}).json()
    route=f"/api/evidence/inventory-observations/{observation['id']}/investigation"
    assert client.get(route).status_code==401
    assert client.get(route,headers=b).status_code==404
    key=headers(a);body={'note':'调查差异'}
    assert client.post(route,headers=headers(b),json=body).status_code==404
    first=client.post(route,headers=key,json=body);assert first.status_code==201
    assert client.post(route,headers=key,json=body).json()==first.json()
    assert client.post(route,headers=headers(a),json=body).json()['code']=='INVESTIGATION_EXISTS'
    ident=first.json()['id'];transition=f'/api/evidence/inventory-investigations/{ident}/transition'
    submit={'version':1,'action':'SUBMIT','note':'说明原因'};submitkey=headers(a)
    assert client.post(transition,headers=submitkey,json=submit).json()['status']=='PENDING_REVIEW'
    assert client.post(transition,headers=submitkey,json=submit).status_code==200
    assert client.post(transition,headers=headers(a),json={'version':2,'action':'REVIEW','note':'自审'}).status_code==403
    assert client.post(transition,headers=headers(b),json={'version':2,'action':'REVIEW','note':'跨组织'}).status_code==404
    assert client.post(transition,headers=headers(r),json={'version':1,'action':'RETURN','note':'版本过期'}).status_code==409
    assert client.post(transition,headers=headers(r),json={'version':2,'action':'RETURN','note':'补充'}).json()['status']=='RETURNED'
    assert client.post(transition,headers=headers(a),json={'version':3,'action':'SUBMIT','note':'补充说明'}).status_code==200
    assert client.post(transition,headers=headers(r),json={'version':4,'action':'REVIEW','note':'已复核说明'}).json()['status']=='REVIEWED'
    assert client.post(transition,headers=headers(r),json={'version':5,'action':'REVIEW','note':'重复'}).status_code==409
    detail=client.get(route,headers=a).json();assert detail['investigation']['status']=='REVIEWED'
    assert [e['action'] for e in detail['events']['items']]==['START','SUBMIT','RETURN','SUBMIT','REVIEW']
    with factory() as db:
        assert db.get(Evidence,item['id']).balance==Decimal('83')
        assert len(db.scalars(select(WeightEvent)).all())==1


def test_zero_difference_and_audit_rollback(context):
    client,factory=context;a=auth(client,'alice');item=setup_item(client,a)
    base=f"/api/evidence/{item['id']}/inventory-observations"
    zero=client.post(base,headers=headers(a),json={'evidence_version':1,'observed_weight':'83','note':'测试'}).json()
    assert client.post(f"/api/evidence/inventory-observations/{zero['id']}/investigation",headers=headers(a),json={'note':'测试'}).json()['code']=='NO_DIFFERENCE'
    obs=client.post(base,headers=headers(a),json={'evidence_version':2,'observed_weight':'82.9','note':'测试'}).json()
    route=f"/api/evidence/inventory-observations/{obs['id']}/investigation";body={'note':'调查'};key=headers(a);engine=factory.kw['bind']
    with engine.begin() as db:db.execute(text("CREATE TRIGGER fail_inv_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'INVENTORY_INVESTIGATION_START' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe:assert safe.post(route,headers=key,json=body).status_code==500
    with engine.begin() as db:db.execute(text('DROP TRIGGER fail_inv_audit'))
    with factory() as db:
        assert db.scalars(select(InventoryInvestigation)).all()==[]
        assert db.scalars(select(InventoryInvestigationEvent)).all()==[]
    assert client.post(route,headers=key,json=body).status_code==201
