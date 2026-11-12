import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from wellspring.audit_actions import ACTION_LABELS, action_name
from wellspring.models import Audit, User
from test_workflow import context, auth


def test_every_literal_audit_action_has_a_chinese_description():
    emitted=set()
    for path in (Path(__file__).resolve().parents[1]/'wellspring').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name):continue
            if node.func.id=='audit' and len(node.args)>2 and isinstance(node.args[2],ast.Constant):emitted.add(node.args[2].value)
            if node.func.id=='Audit':
                emitted.update(item.value.value for item in node.keywords if item.arg=='action' and isinstance(item.value,ast.Constant))
            if node.func.id=='store' and len(node.args)>5 and isinstance(node.args[5],ast.Constant):emitted.add(node.args[5].value)
            if path.name=='places.py' and node.func.id=='saved' and len(node.args)>4 and isinstance(node.args[4],ast.Constant):emitted.add('PLACE_'+node.args[4].value)
    assert emitted<=ACTION_LABELS.keys(),emitted-ACTION_LABELS.keys()
    for code,label in ACTION_LABELS.items():
        assert any('\u4e00'<=letter<='\u9fff' for letter in label),code
        assert not any('a'<=letter.lower()<='z' for letter in label),code
    assert action_name('PLACE_INCIDENT_CONFIRM')=='核验场所事件'
    assert action_name('EVIDENCE_LIST')=='查询历史证物'
    assert action_name('UNREGISTERED_LEGACY_ACTION')=='其他操作'


def seed(factory):
    midnight=datetime(2026,11,10,16,tzinfo=timezone.utc)
    with factory() as db:
        a=db.scalar(select(User).where(User.username=='alice'));b=db.scalar(select(User).where(User.username=='bob'))
        for user,count in [(a,32),(b,5)]:
            db.add_all([Audit(actor_id=user.id,org_id=user.org_id,action='CASE_CREATE',object_id=f'synthetic-{index:02d}',created_at=midnight+timedelta(minutes=index)) for index in range(count)])
        for offset,identity in [(-1,'before-local-day'),(86400,'after-local-day')]:
            db.add(Audit(actor_id=a.id,org_id=a.org_id,action='CASE_CREATE',object_id=identity,created_at=midnight+timedelta(seconds=offset)))
        db.add(Audit(actor_id=a.id,org_id=a.org_id,action='UNKNOWN_OLD_ACTION',object_id='unknown-history'))
        db.commit()


def test_personal_search_translates_filters_dates_and_pages_without_exposing_other_people(context):
    client,factory=context;seed(factory);a=auth(client,'alice');b=auth(client,'bob')
    assert client.get('/api/audit/mine').status_code==401
    params={'action':'创建案件记录','start_date':'2026-11-11','end_date':'2026-11-11'}
    first=client.get('/api/audit/mine',headers=a,params=params).json()
    assert first['total']==32 and first['page_size']==15 and len(first['items'])==15 and first['has_more']
    assert all(row['action']=='CASE_CREATE' and row['action_name']=='创建案件记录' for row in first['items'])
    second=client.get('/api/audit/mine',headers=a,params={**params,'page':2}).json()
    assert len(second['items'])==15 and not {row['id'] for row in first['items']} & {row['id'] for row in second['items']}
    third=client.get('/api/audit/mine',headers=a,params={**params,'page':3}).json()
    assert len(third['items'])==2 and not third['has_more']
    single=client.get('/api/audit/mine',headers=a,params={**params,'object_id':'synthetic-07'}).json()
    assert single['total']==1 and single['items'][0]['object_id']=='synthetic-07'
    assert client.get('/api/audit/mine',headers=b,params=params).json()['total']==5
    assert client.get('/api/audit/mine',headers=a,params={'action':'%'}).json()['total']==0
    assert client.get('/api/audit/mine',headers=a,params={'object_id':'%'}).json()['total']==0
    for invalid in [{'start_date':'invalid'},{'start_date':'2026-11-12','end_date':'2026-11-11'},{'end_date':'9999-12-31'}]:
        assert client.get('/api/audit/mine',headers=a,params=invalid).status_code==422
    with factory() as db:
        assert db.scalar(select(Audit).where(Audit.object_id=='synthetic-07')).action=='CASE_CREATE'
        assert db.scalar(select(Audit).where(Audit.action=='AUDIT_SELF_VIEW')).object_id not in {'创建案件记录','synthetic-07'}


def test_system_search_uses_chinese_descriptions_and_fifteen_row_defaults(context):
    client,factory=context;seed(factory);a=auth(client,'alice');b=auth(client,'bob');path='/api/admin/audit/search'
    assert client.post(path,headers=b,json={}).status_code==403
    with factory() as db:
        actor=db.scalar(select(User).where(User.username=='alice'));actor.is_admin=True;db.commit()
    result=client.post(path,headers=a,json={'username':'bob','action':'创建案件'}).json()
    assert result['total']==5 and result['page_size']==15
    assert all(row['action_name']=='创建案件记录' and row['username']=='bob' for row in result['items'])
    page=client.post(path,headers=a,json={'username':'alice','action':'case_create'}).json()
    assert page['total']==34 and len(page['items'])==15 and page['has_more']
    unknown=client.post(path,headers=a,json={'action':'UNKNOWN_OLD_ACTION'}).json()['items'][0]
    assert unknown['action_name']=='其他操作' and unknown['action']=='UNKNOWN_OLD_ACTION'
