from sqlalchemy import select
from wellspring.models import Audit, Case
from test_workflow import context, auth, headers


def test_csv_preview_is_bounded_and_never_writes_cases(context):
    client,factory=context;a=auth(client,'alice')
    route='/api/imports/case-csv-preview'
    assert client.post(route,json={'content':'案件编号,案件名称'}).status_code==401
    csv='案件编号,案件名称\nA-1,虚构案件\nA-1,重复\nA-2,=公式\n缺列\n'
    response=client.post(route,headers=a,json={'content':csv})
    assert response.status_code==200
    data=response.json();assert (data['total'],data['valid_count'],data['invalid_count'])==(4,1,3)
    assert data['mode']=='PREVIEW_ONLY' and len(data['sha256'])==64
    multiline=client.post(route,headers=a,json={'content':'案件编号,案件名称\nA-1,"第一行\n第二行"\nA-2,下一条'}).json()
    assert [row['row'] for row in multiline['rows']]==[2,4]
    assert client.post(route,headers=a,json={'content':'错误,表头\nx,y'}).status_code==422
    assert client.post(route,headers=a,json={'content':'案件编号,案件名称\n"unterminated'}).status_code==422
    assert client.post(route,headers=a,json={'content':'案件编号,案件名称\n'+'x'*100000}).status_code in (413,422)
    with factory() as db:
        assert db.scalars(select(Case)).all()==[]
        audit=db.scalars(select(Audit).where(Audit.action=='IMPORT_CASE_PREVIEW')).all()
        assert len(audit)==2 and all('虚构案件' not in e.object_id for e in audit)


def test_audit_self_scope_and_ai_unavailable(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob')
    client.post('/api/cases',headers=headers(a),json={'number':'A-1','title':'虚构'})
    client.post('/api/cases',headers=headers(b),json={'number':'B-1','title':'虚构'})
    assert client.get('/api/audit/mine').status_code==401
    result=client.get('/api/audit/mine?page_size=1',headers=a).json()
    assert len(result['items'])==1 and result['has_more']
    ids={row['id'] for row in client.get('/api/audit/mine',headers=a).json()['items']}
    with factory() as db:
        audits=db.scalars(select(Audit).where(Audit.id.in_(ids))).all()
        assert all(row.actor_id==audits[0].actor_id and row.org_id==audits[0].org_id for row in audits)
    assert client.get('/api/audit/mine?page_size=101',headers=a).status_code==422
    assert client.get('/api/ai/status').status_code==401
    assert client.get('/api/ai/status',headers=a).json()['available'] is False
