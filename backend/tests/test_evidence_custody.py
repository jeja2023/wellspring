from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.main import app
from wellspring.models import CustodyEvent, CustodyHandover, Evidence, EvidenceCustody, User, WeightEvent
from wellspring.security import password_hash
from test_workflow import context,auth,headers
from test_evidence_inventory import setup_item


def prepare(factory):
    with factory() as db:
        alice=db.scalar(select(User).where(User.username=='alice'))
        receiver=User(username='receiver',org_id=alice.org_id,password_hash=password_hash('test-password-123'))
        db.add(receiver);db.commit();return alice.id,receiver.id


def test_custody_two_person_reject_then_accept(context):
    client,factory=context;alice_id,receiver_id=prepare(factory)
    a,r,b=auth(client,'alice'),auth(client,'receiver'),auth(client,'bob');item=setup_item(client,a);eid=item['id']
    get=f'/api/evidence/{eid}/custody';base=f'{get}/baseline'
    assert client.get(get).status_code==401
    assert client.get(get,headers=b).status_code==404
    assert client.get(get,headers=a).json()['custody'] is None
    assert client.post(base,headers=headers(a),json={'evidence_version':2,'note':'测试'}).status_code==409
    key=headers(a);body={'evidence_version':1,'note':'虚构基线'}
    first=client.post(base,headers=key,json=body);assert first.status_code==201
    assert client.post(base,headers=key,json=body).json()==first.json()
    assert client.post(base,headers=headers(r),json=body).status_code==409
    hand=f'/api/evidence/{eid}/handovers';payload={'custody_version':1,'to_user_id':receiver_id,'note':'虚构交出'}
    assert client.post(hand,headers=headers(r),json=payload).status_code==403
    assert client.post(hand,headers=headers(a),json={**payload,'to_user_id':alice_id}).status_code==422
    hkey=headers(a);proposed=client.post(hand,headers=hkey,json=payload);assert proposed.status_code==201
    assert client.post(hand,headers=hkey,json=payload).json()==proposed.json()
    current=client.get(get,headers=a).json();assert current['custody']['custodian_id']==alice_id and current['custody']['version']==2
    assert client.post(hand,headers=headers(a),json={**payload,'custody_version':2}).status_code==409
    respond=f"/api/evidence/handovers/{proposed.json()['id']}/respond";reply={'version':1,'action':'REJECT','note':'虚构拒收'}
    assert client.post(respond,headers=headers(a),json=reply).status_code==403
    assert client.post(respond,headers=headers(b),json=reply).status_code==404
    rkey=headers(r);assert client.post(respond,headers=rkey,json=reply).json()['status']=='REJECTED'
    assert client.post(respond,headers=rkey,json=reply).status_code==200
    state=client.get(get,headers=a).json();assert state['custody']['custodian_id']==alice_id and state['custody']['version']==3 and state['pending'] is None
    second=client.post(hand,headers=headers(a),json={**payload,'custody_version':3}).json()
    assert client.post(f"/api/evidence/handovers/{second['id']}/respond",headers=headers(r),json={'version':1,'action':'ACCEPT','note':'虚构接收'}).json()['status']=='ACCEPTED'
    state=client.get(get,headers=r).json();assert state['custody']['custodian_id']==receiver_id and state['pending'] is None
    history=client.get(hand,headers=a).json();assert history['total']==2
    assert {row['status'] for row in history['items']}=={'REJECTED','ACCEPTED'}
    assert all(row['from_user_id']==alice_id and row['to_user_id']==receiver_id and row['response_note'] for row in history['items'])
    assert client.get(hand,headers=b).status_code==404
    with factory() as db:
        assert db.get(Evidence,eid).balance==Decimal('83')
        assert len(db.scalars(select(WeightEvent)).all())==1
        assert len(db.scalars(select(CustodyEvent)).all())==5


def test_handover_audit_failure_rolls_back(context):
    client,factory=context;alice_id,receiver_id=prepare(factory);a=auth(client,'alice');item=setup_item(client,a);eid=item['id']
    client.post(f'/api/evidence/{eid}/custody/baseline',headers=headers(a),json={'evidence_version':1,'note':'基线'})
    engine=factory.kw['bind']
    with engine.begin() as db:db.execute(text("CREATE TRIGGER fail_custody_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'CUSTODY_HANDOVER_CREATE' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    key=headers(a);body={'custody_version':1,'to_user_id':receiver_id,'note':'测试'};route=f'/api/evidence/{eid}/handovers'
    with TestClient(app,raise_server_exceptions=False) as safe:assert safe.post(route,headers=key,json=body).status_code==500
    with engine.begin() as db:db.execute(text('DROP TRIGGER fail_custody_audit'))
    with factory() as db:
        assert db.scalars(select(CustodyHandover)).all()==[]
        assert db.scalar(select(EvidenceCustody)).version==1
    assert client.post(route,headers=key,json=body).status_code==201
