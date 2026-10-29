from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.main import app
from wellspring.models import IdempotencyRecord, PersonDraft
from test_workflow import context, auth, headers


def test_person_drafts_scope_pagination_and_idempotency(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob')
    assert client.get('/api/person-drafts').status_code==401
    body={'name':'虚构姓名','source':'虚构来源'};same=headers(a)
    first=client.post('/api/person-drafts',headers=same,json=body)
    assert first.status_code==201 and first.json()['verification_status']=='UNVERIFIED'
    assert client.post('/api/person-drafts',headers=same,json=body).json()==first.json()
    assert client.post('/api/person-drafts',headers=same,json={**body,'source':'不同'}).json()['code']=='IDEMPOTENCY_CONFLICT'
    assert client.post('/api/person-drafts',headers=headers(a),json={'name':'  ','source':'x'}).status_code==422
    assert client.post('/api/person-drafts',headers=headers(a),json=body).status_code==201 # 不按姓名自动去重
    assert client.get('/api/person-drafts?page_size=1',headers=a).json()['total']==2
    assert client.get('/api/person-drafts',headers=b).json()['total']==0
    assert client.get('/api/person-drafts?page_size=101',headers=a).status_code==422
    with factory() as db: assert len(db.scalars(select(PersonDraft)).all())==2


def test_person_audit_failure_rolls_back(context):
    client,factory=context;a=auth(client,'alice');engine=factory.kw['bind']
    with engine.begin() as db: db.execute(text("CREATE TRIGGER fail_person_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'PERSON_DRAFT_CREATE' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    body={'name':'虚构姓名','source':'虚构来源'};same=headers(a)
    with TestClient(app,raise_server_exceptions=False) as safe:
        assert safe.post('/api/person-drafts',headers=same,json=body).status_code==500
    with engine.begin() as db: db.execute(text('DROP TRIGGER fail_person_audit'))
    with factory() as db:
        assert db.scalars(select(PersonDraft)).all()==[]
        assert db.scalars(select(IdempotencyRecord).where(IdempotencyRecord.operation=='PERSON_DRAFT_CREATE')).all()==[]
    assert client.post('/api/person-drafts',headers=same,json=body).status_code==201


def test_person_search_scope_literal_and_pagination(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob')
    for name,source in [('虚构甲%','来源甲'),('虚构甲二','来源乙'),('虚构乙','来源甲')]:
        assert client.post('/api/person-drafts',headers=headers(a),json={'name':name,'source':source}).status_code==201
    client.post('/api/person-drafts',headers=headers(b),json={'name':'虚构甲其他组织','source':'来源甲'})
    route='/api/person-drafts/search'
    first=client.post(route,headers=a,json={'keyword':'虚构甲','page':1,'page_size':1}).json()
    second=client.post(route,headers=a,json={'keyword':'虚构甲','page':2,'page_size':1}).json()
    assert first['total']==2 and first['has_more'] and second['total']==2 and not second['has_more']
    assert first['items'][0]['id']!=second['items'][0]['id']
    assert client.post(route,headers=a,json={'keyword':'%'}).json()['total']==1
    assert client.post(route,headers=b,json={'keyword':'来源甲'}).json()['total']==1
    assert client.post(route,json={}).status_code==401
    assert client.post(route,headers=a,json={'keyword':'x'*101}).status_code==422
