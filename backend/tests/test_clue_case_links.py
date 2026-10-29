from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.main import app
from wellspring.models import Case, Clue, ClueCaseLink, IntelligenceEvent
from test_workflow import context, auth, headers


def seed(client, actor):
    case = client.post('/api/cases',headers=headers(actor),json={'number':'DEV-1','title':'虚构案件'}).json()
    clue = client.post('/api/intelligence/clues',headers=headers(actor),json={'title':'虚构线索','source':'虚构来源','summary':'测试摘要'}).json()
    review=client.post(f"/api/intelligence/clues/{clue['id']}/review",headers=headers(actor),json={'version':1,'note':'开发验证'})
    assert review.status_code == 200
    return case, review.json()


def test_link_revoke_relink_and_scope(context):
    client, factory = context
    a,b=auth(client,'alice'),auth(client,'bob')
    case,clue=seed(client,a)
    other_case=client.post('/api/cases',headers=headers(b),json={'number':'B-1','title':'其他组织'}).json()
    route=f"/api/intelligence/clues/{clue['id']}/case-links"
    body={'case_id':case['id'],'clue_version':clue['version'],'basis':'虚构依据'}
    assert client.post(route,headers=headers(b),json=body).status_code==404
    assert client.post(route,headers=headers(a),json={**body,'case_id':other_case['id']}).status_code==404
    assert client.post(route,headers=headers(a),json={**body,'basis':'   '}).status_code==422
    same=headers(a)
    response=client.post(route,headers=same,json=body)
    assert response.status_code==201
    link=response.json()
    assert client.post(route,headers=same,json=body).json()['id']==link['id']
    assert client.post(route,headers=same,json={**body,'basis':'不同'}).json()['code']=='IDEMPOTENCY_CONFLICT'
    assert client.post(route,headers=headers(a),json=body).status_code==409
    duplicate=client.post(route,headers=headers(a),json={**body,'clue_version':3})
    assert duplicate.status_code==409 and duplicate.json()['code']=='LINK_EXISTS'
    detail=client.get(f"/api/intelligence/clues/{clue['id']}/detail",headers=a).json()
    assert detail['clue']['version']==3  # 重复关联被拒绝时，线索版本回滚。
    assert client.get(route,headers=b).status_code==404
    revoked_route=f"/api/intelligence/case-links/{link['id']}/revoke"
    assert client.post(revoked_route,headers=headers(b),json={'version':1,'reason':'测试'}).status_code==404
    assert client.post(revoked_route,headers=headers(a),json={'version':2,'reason':'测试'}).status_code==409
    revoke_headers=headers(a); revoke_body={'version':1,'reason':'关联有误'}
    result=client.post(revoked_route,headers=revoke_headers,json=revoke_body)
    assert result.json()['status']=='REVOKED' and result.json()['revoke_reason']=='关联有误'
    assert client.post(revoked_route,headers=revoke_headers,json=revoke_body).status_code==200
    relink=client.post(route,headers=headers(a),json={**body,'clue_version':3,'basis':'重新核对'})
    assert relink.status_code==201 and relink.json()['id']!=link['id']
    links=client.get(route,headers=a).json()['items']
    assert {x['status'] for x in links}=={'ACTIVE','REVOKED'}
    with factory() as db:
        events=db.scalars(select(IntelligenceEvent).where(IntelligenceEvent.clue_id==clue['id'])).all()
        assert len([e for e in events if e.action=='CASE_LINKED'])==2
        assert len([e for e in events if e.action=='CASE_LINK_REVOKED'])==1
        assert {e.related_link_id for e in events if e.related_link_id}=={link['id'],relink.json()['id']}
        assert db.get(Case,case['id']).status=='DRAFT'


def test_recheck_case_scope_and_atomic_audit(context):
    client, factory=context
    a,b=auth(client,'alice'),auth(client,'bob')
    case,clue=seed(client,a)
    other_case=client.post('/api/cases',headers=headers(b),json={'number':'B-1','title':'其他组织'}).json()
    route=f"/api/intelligence/clues/{clue['id']}/case-links"
    body={'case_id':case['id'],'clue_version':2,'basis':'开发测试'}
    engine=factory.kw['bind']
    with engine.begin() as db:
        db.execute(text("CREATE TRIGGER fail_link_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'CLUE_CASE_LINK_CREATE' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    key=headers(a)
    with TestClient(app,raise_server_exceptions=False) as safe:
        assert safe.post(route,headers=key,json=body).status_code==500
    with engine.begin() as db:
        db.execute(text('DROP TRIGGER fail_link_audit'))
    with factory() as db:
        assert db.get(Clue,clue['id']).version==2
        assert db.scalars(select(ClueCaseLink)).all()==[]
    link=client.post(route,headers=key,json=body).json()
    with factory() as db:
        case_row=db.get(Case,case['id'])
        case_row.org_id=db.get(Case,other_case['id']).org_id
        db.commit()
    assert client.get(route,headers=a).json()['total']==0
    assert client.post(f"/api/intelligence/case-links/{link['id']}/revoke",headers=headers(a),json={'version':1,'reason':'测试'}).status_code==404
    assert client.post(route,headers=key,json=body).status_code==404
    assert client.get(route).status_code==401
