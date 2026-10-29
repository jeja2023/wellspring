from sqlalchemy import select, text
from fastapi.testclient import TestClient
from wellspring.main import app
from wellspring.models import Case, CaseRelation, CaseRelationEvent, IdempotencyRecord
from test_workflow import context, auth, headers

def create_case(client, actor, number):
    return client.post('/api/cases',headers=headers(actor),json={'number':number,'title':'虚构案件'}).json()

def test_symmetric_relations_and_revocation(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob')
    one=create_case(client,a,'A-1');two=create_case(client,a,'A-2');foreign=create_case(client,b,'B-1')
    url=f"/api/cases/{one['id']}/relations";body={'target_case_id':two['id'],'relation_type':'RELATED_TO','basis':'虚构依据'};same=headers(a)
    assert client.post(url,json=body).status_code==401
    assert client.post(url,headers=headers(b),json=body).status_code==404
    assert client.post(url,headers=headers(a),json={**body,'target_case_id':foreign['id']}).status_code==404
    assert client.post(url,headers=headers(a),json={**body,'target_case_id':one['id']}).status_code==422
    assert client.post(url,headers=headers(a),json={**body,'relation_type':'MERGED_INTO'}).status_code==422
    first=client.post(url,headers=same,json=body);assert first.status_code==201
    assert client.post(url,headers=same,json=body).json()==first.json()
    assert client.post(url,headers=same,json={**body,'basis':'不同'}).json()['code']=='IDEMPOTENCY_CONFLICT'
    reverse=f"/api/cases/{two['id']}/relations"
    assert client.post(reverse,headers=headers(a),json={**body,'target_case_id':one['id']}).json()['code']=='RELATION_EXISTS'
    assert client.get(reverse,headers=a).json()['items'][0]['other_case_id']==one['id']
    coop=client.post(url,headers=headers(a),json={**body,'relation_type':'COOPERATE_WITH'});assert coop.status_code==201
    rid=first.json()['id'];rurl=f'/api/cases/relations/{rid}/revoke'
    assert client.post(rurl,headers=headers(b),json={'version':1,'reason':'测试'}).status_code==404
    assert client.post(rurl,headers=headers(a),json={'version':2,'reason':'测试'}).status_code==409
    key=headers(a);revoke={'version':1,'reason':'关联更正'}
    assert client.post(rurl,headers=key,json=revoke).json()['relation_status']=='REVOKED'
    assert client.post(rurl,headers=key,json=revoke).status_code==200
    assert client.post(url,headers=headers(a),json=body).status_code==201
    assert client.get(url,headers=a).json()['total']==3
    with factory() as db:
        assert db.get(Case,one['id']).status=='DRAFT'
        events=db.scalars(select(CaseRelationEvent).where(CaseRelationEvent.relation_id==rid)).all()
        assert [e.action for e in events]==['CREATE','REVOKE']

def test_relation_audit_failure_and_access_recheck(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob')
    one=create_case(client,a,'A-1');two=create_case(client,a,'A-2');foreign=create_case(client,b,'B-1')
    url=f"/api/cases/{one['id']}/relations";body={'target_case_id':two['id'],'relation_type':'RELATED_TO','basis':'依据'};key=headers(a)
    engine=factory.kw['bind']
    with engine.begin() as db:db.execute(text("CREATE TRIGGER fail_case_relation_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'CASE_RELATION_CREATE' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe:assert safe.post(url,headers=key,json=body).status_code==500
    with engine.begin() as db:db.execute(text('DROP TRIGGER fail_case_relation_audit'))
    with factory() as db:
        assert db.scalars(select(CaseRelation)).all()==[]
        assert db.scalars(select(IdempotencyRecord).where(IdempotencyRecord.operation=='CASE_RELATION_CREATE')).all()==[]
    relation=client.post(url,headers=key,json=body).json()
    with factory() as db:
        db.get(Case,two['id']).org_id=db.get(Case,foreign['id']).org_id;db.commit()
    assert client.get(url,headers=a).json()['total']==0
    assert client.post(url,headers=key,json=body).status_code==404
    assert client.post(f"/api/cases/relations/{relation['id']}/revoke",headers=headers(a),json={'version':1,'reason':'x'}).status_code==404
