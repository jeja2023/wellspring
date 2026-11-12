from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import select
from wellspring.access_models import Role
from wellspring.demo_data import seed_demo_data
from wellspring.models import Clue, InvestigationTask, User
from wellspring.workbench import overview
from test_workflow import context, auth, headers


def seeded(factory):
    with factory() as db:
        actor=db.scalar(select(User).where(User.username=='alice'));actor.is_admin=True
        seed_demo_data(db,actor);db.commit();return actor.id


def test_workbench_combines_only_actionable_scoped_items(context):
    client,factory=context;actor_id=seeded(factory);login=auth(client,'alice')
    response=client.get('/api/workbench/tasks?page_size=1',headers=login)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['total']>len(data['items']) and data['counts']['overdue']>1
    assert data['has_more'] and data['items'][0]['overdue_days']>0
    assert {item['key'] for item in data['available_modules']}=={'intelligence','persons','places','wastewater'}
    for module in ['intelligence','persons','places','wastewater']:
        for queue in ['todo','review']:
            page=client.get(f'/api/workbench/tasks?queue={queue}&module={module}&page_size=50',headers=login).json()
            assert all(item['module']==module and item['queue']==queue for item in page['items'])
            assert page['counts'][queue]==page['total']
    reviews=client.get('/api/workbench/tasks?queue=review&page_size=50',headers=login).json()
    assert reviews['total']>0
    with factory() as db:
        for item in reviews['items']:
            if item['kind']=='investigation':assert db.get(InvestigationTask,item['id']).last_submitter_id!=actor_id
    for item in reviews['items']:
        if item['kind']=='person-record':
            path=f"/api/person-drafts/{item['resource_id']}/records?kind={item['tab']}&focus_id={item['id']}"
        elif item['kind']=='incident':
            path=f"/api/places/{item['resource_id']}/incidents?focus_id={item['id']}"
        else:continue
        focused=client.get(path,headers=login)
        assert focused.status_code==200 and [row['id'] for row in focused.json()['items']]==[item['id']],focused.text
        assert client.get(path,headers=auth(client,'bob')).status_code==404
        break
    # Existing mutation API still performs its usual actor/version checks.
    investigation=next(item for item in reviews['items'] if item['kind']=='investigation')
    with factory() as db:version=db.get(InvestigationTask,investigation['id']).version
    result=client.post('/api/intelligence/tasks/'+investigation['id']+'/transition',headers=headers(login),
                       json={'version':version,'action':'CLOSE','note':'测试独立复核'})
    assert result.status_code==200,result.text
    remaining=client.get('/api/workbench/tasks?queue=review&module=intelligence&page_size=50',headers=login).json()
    assert investigation['id'] not in {item['id'] for item in remaining['items']}
    outsider=auth(client,'bob')
    other=client.get('/api/workbench/tasks',headers=outsider)
    assert other.status_code==200 and other.json()['total']==0
    assert client.get('/api/workbench/tasks').status_code==401
    assert client.get('/api/workbench/tasks?module=unknown',headers=login).status_code==422


def test_read_only_and_revoked_roles_do_not_expose_action_queues(context):
    client,factory=context;actor_id=seeded(factory)
    with factory() as db:
        actor=db.get(User,actor_id);actor.is_admin=False
        role=Role(code='workbench_reader',name='只读',permissions_json=json.dumps(['intelligence.read','persons.read','persons.health','places.read','wastewater.read']))
        db.add(role);db.flush();actor.role_id=role.id;db.commit();role_id=role.id
    login=auth(client,'alice')
    data=client.get('/api/workbench/tasks',headers=login).json()
    assert data['items']==[] and data['available_modules']==[] and not any(data['counts'].values())
    with factory() as db:
        db.get(Role,role_id).permissions_json=json.dumps(['places.read','places.write']);db.commit()
    data=client.get('/api/workbench/tasks',headers=login).json()
    assert data['items'] and all(item['module']=='places' for item in data['items'])
    with factory() as db:db.get(Role,role_id).active=False;db.commit()
    assert client.get('/api/workbench/tasks',headers=login).json()['total']==0


def test_deadline_boundary_counts_all_pages_and_skips_own_or_unknown_reviews(context):
    client,factory=context
    instant=datetime(2026,11,12,16,0,tzinfo=timezone.utc)  # 11/13 00:00 Beijing
    with factory() as db:
        actor=db.scalar(select(User).where(User.username=='alice'))
        for index in range(24):
            clue=Clue(org_id=actor.org_id,title=f'期限-{index}',summary='合成',source='合成',created_by=actor.id)
            db.add(clue);db.flush()
            status='PENDING_REVIEW' if index>=21 else 'OPEN'
            db.add(InvestigationTask(org_id=actor.org_id,clue_id=clue.id,objective='合成',assignee_id=actor.id,
                                     due_date=instant.date()+timedelta(days=index%3),status=status,
                                     last_submitter_id=actor.id if index==21 else None))
        db.commit()
        before=overview(db,actor,queue='overdue',page_size=2,instant=instant-timedelta(seconds=1))
        assert before['counts']==dict(todo=21,review=0,overdue=0,due_today=7)
        after=overview(db,actor,queue='overdue',page_size=2,instant=instant)
        assert after['counts']==dict(todo=21,review=0,overdue=7,due_today=7)
        assert len(after['items'])==2 and after['has_more']
        assert all(item['overdue_days']==1 for item in after['items'])
        last=overview(db,actor,queue='overdue',page_size=2,page=999,instant=instant)
        assert last['page']==4 and len(last['items'])==1
