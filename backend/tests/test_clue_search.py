from sqlalchemy import select
from wellspring.models import Audit
from test_workflow import context, auth, headers


def test_search_filters_after_scope_and_paginates(context):
    client, factory = context
    alice, bob = auth(client, "alice"), auth(client, "bob")
    records = [
        {"title":"虚构甲%","source":"来源一","summary":"秘密仅在摘要"},
        {"title":"虚构甲二","source":"来源二","summary":"普通"},
        {"title":"虚构乙","source":"来源一","summary":"普通"},
    ]
    created = [client.post('/api/intelligence/clues',headers=headers(alice),json=x).json() for x in records]
    client.post('/api/intelligence/clues',headers=headers(bob),json={"title":"虚构甲外部","source":"来源一","summary":"普通"})
    assert client.post(f"/api/intelligence/clues/{created[0]['id']}/review",headers=headers(alice),json={"version":1,"note":"核验"}).status_code==200
    search=lambda body, actor=alice: client.post('/api/intelligence/clues/search',headers=actor,json=body)
    first=search({"keyword":"虚构甲","page":1,"page_size":1}).json()
    second=search({"keyword":"虚构甲","page":2,"page_size":1}).json()
    assert first['total']==2 and first['has_more'] and len(first['items'])==1
    assert second['total']==2 and not second['has_more'] and first['items'][0]['id']!=second['items'][0]['id']
    assert search({"keyword":"来源一","status":"REVIEWED"}).json()['total']==1
    assert search({"keyword":"%"}).json()['total']==1
    assert search({"keyword":"秘密仅在摘要"}).json()['total']==0
    assert search({"keyword":"虚构甲"},bob).json()['total']==1
    assert client.post('/api/intelligence/clues/search',json={}).status_code==401
    assert search({"status":"UNKNOWN"}).status_code==422
    assert search({"keyword":"x"*101}).status_code==422
    assert search({"page_size":101}).status_code==422
    with factory() as db:
        audit=db.scalars(select(Audit).where(Audit.action=='CLUE_SEARCH')).all()
        assert len(audit)>=6
        assert all('虚构甲' not in e.object_id for e in audit)
