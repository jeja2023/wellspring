from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.main import app
from wellspring.models import Case, PersonDraft, PersonCaseCandidate, PersonCaseCandidateEvent
from test_workflow import context,auth,headers


def test_candidates_are_not_formal_and_respect_both_sides(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob')
    person=client.post('/api/person-drafts',headers=headers(a),json={'name':'虚构','source':'虚构'}).json()
    case=client.post('/api/cases',headers=headers(a),json={'number':'A-1','title':'虚构'}).json()
    foreign=client.post('/api/cases',headers=headers(b),json={'number':'B-1','title':'虚构'}).json()
    route=f"/api/person-drafts/{person['id']}/case-candidates";body={'case_id':case['id'],'person_version':1,'basis':'虚构依据'};key=headers(a)
    assert client.post(route,json=body).status_code==401
    assert client.post(route,headers=headers(b),json=body).status_code==404
    assert client.post(route,headers=headers(a),json={**body,'case_id':foreign['id']}).status_code==404
    assert client.post(route,headers=headers(a),json={**body,'basis':' '}).status_code==422
    first=client.post(route,headers=key,json=body);assert first.status_code==201
    assert first.json()['verification']=='CANDIDATE'
    assert client.post(route,headers=key,json=body).json()==first.json()
    assert client.post(route,headers=headers(a),json=body).json()['code']=='VERSION_CONFLICT'
    assert client.post(route,headers=headers(a),json={**body,'person_version':2}).json()['code']=='CANDIDATE_EXISTS'
    with factory() as db: assert db.get(PersonDraft,person['id']).version==2
    rid=first.json()['id'];rev=f'/api/person-drafts/case-candidates/{rid}/revoke';rkey=headers(a);payload={'version':1,'reason':'虚构撤销'}
    assert client.post(rev,headers=headers(b),json=payload).status_code==404
    assert client.post(rev,headers=rkey,json=payload).json()['status']=='REVOKED'
    assert client.post(rev,headers=rkey,json=payload).status_code==200
    assert client.post(route,headers=headers(a),json={**body,'person_version':2}).status_code==201
    with factory() as db:
        assert db.get(PersonDraft,person['id']).verification_status=='UNVERIFIED'
        assert db.get(Case,case['id']).status=='DRAFT'
        assert len(db.scalars(select(PersonCaseCandidateEvent).where(PersonCaseCandidateEvent.candidate_id==rid)).all())==2
    with factory() as db:
        db.get(Case,case['id']).org_id=db.get(Case,foreign['id']).org_id;db.commit()
    assert client.get(route,headers=a).json()['total']==0
    assert client.post(rev,headers=rkey,json=payload).status_code==404


def test_audit_failure_rolls_back_candidate_and_person_version(context):
    client,factory=context;a=auth(client,'alice')
    person=client.post('/api/person-drafts',headers=headers(a),json={'name':'虚构','source':'虚构'}).json()
    case=client.post('/api/cases',headers=headers(a),json={'number':'A-1','title':'虚构'}).json()
    url=f"/api/person-drafts/{person['id']}/case-candidates";body={'case_id':case['id'],'person_version':1,'basis':'依据'};key=headers(a)
    engine=factory.kw['bind']
    with engine.begin() as db:db.execute(text("CREATE TRIGGER fail_person_link_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'PERSON_CASE_CANDIDATE_CREATE' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe: assert safe.post(url,headers=key,json=body).status_code==500
    with engine.begin() as db:db.execute(text('DROP TRIGGER fail_person_link_audit'))
    with factory() as db:
        assert db.get(PersonDraft,person['id']).version==1
        assert db.scalars(select(PersonCaseCandidate)).all()==[]
    assert client.post(url,headers=key,json=body).status_code==201
