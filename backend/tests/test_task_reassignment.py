from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.main import app
from wellspring.models import IntelligenceEvent, InvestigationTask, Organization, User
from wellspring.security import password_hash
from test_workflow import context, auth, headers


def create_person(factory, username, org_name, active=True):
    with factory() as db:
        org = db.scalar(select(Organization).where(Organization.name == org_name))
        person = User(username=username, org_id=org.id, active=active, password_hash=password_hash("test-password-123"))
        db.add(person); db.commit()
        return person.id


def seed_task(client, factory):
    alice=auth(client,"alice")
    with factory() as db:
        alice_id=db.scalar(select(User.id).where(User.username=="alice"))
    clue=client.post('/api/intelligence/clues',headers=headers(alice),json={'title':'虚构线索','summary':'虚构内容','source':'虚构来源'}).json()
    cid=clue['id']
    assert client.post(f'/api/intelligence/clues/{cid}/review',headers=headers(alice),json={'version':1,'note':'开发验证'}).status_code==200
    task=client.post(f'/api/intelligence/clues/{cid}/tasks',headers=headers(alice),json={'clue_version':2,'objective':'虚构核查','assignee_id':alice_id}).json()
    return alice,alice_id,cid,task


def test_reassign_scope_history_and_worklist(context):
    client,factory=context
    new_id=create_person(factory,'handler','A')
    disabled_id=create_person(factory,'disabled','A',False)
    outside_id=create_person(factory,'outside','B')
    alice,alice_id,cid,task=seed_task(client,factory)
    handler=auth(client,'handler'); outsider=auth(client,'bob')
    url=f"/api/intelligence/tasks/{task['id']}/reassign"
    body={'version':1,'assignee_id':new_id,'reason':'虚构交接'}
    assert client.post(url,json=body).status_code==401
    assert client.post(url,headers=headers(outsider),json=body).status_code==404
    assert client.post(url,headers=headers(alice),json={**body,'assignee_id':outside_id}).status_code==404
    assert client.post(url,headers=headers(alice),json={**body,'assignee_id':disabled_id}).status_code==404
    assert client.post(url,headers=headers(alice),json={**body,'assignee_id':alice_id}).json()['code']=='SAME_ASSIGNEE'
    assert client.post(url,headers=headers(alice),json={**body,'reason':'  '}).status_code==422
    same=headers(alice)
    changed=client.post(url,headers=same,json=body)
    assert changed.status_code==200 and changed.json()['version']==2
    assert changed.json()['assignee_id']==new_id and changed.json()['status']=='OPEN'
    assert client.post(url,headers=same,json=body).json()==changed.json()
    assert client.post(url,headers=same,json={**body,'reason':'其他原因'}).json()['code']=='IDEMPOTENCY_CONFLICT'
    assert client.post(url,headers=headers(alice),json={'version':1,'assignee_id':alice_id,'reason':'过期'}).status_code==409
    assert client.get('/api/intelligence/tasks/mine',headers=alice).json()['total']==0
    assert client.get('/api/intelligence/tasks/mine',headers=handler).json()['total']==1
    timeline=client.get(f'/api/intelligence/clues/{cid}/detail',headers=alice).json()['events']['items']
    event=next(e for e in timeline if e['action']=='REASSIGN')
    assert (event['assignee_before_id'],event['assignee_after_id'],event['note'])==(alice_id,new_id,'虚构交接')
    submit={'version':2,'action':'SUBMIT','result':'NO_FINDING','note':'虚构结果'}
    assert client.post(f"/api/intelligence/tasks/{task['id']}/transition",headers=headers(alice),json=submit).status_code==403
    assert client.post(f"/api/intelligence/tasks/{task['id']}/transition",headers=headers(handler),json=submit).status_code==200
    assert client.post(url,headers=headers(alice),json={'version':3,'assignee_id':alice_id,'reason':'复核中不能更改'}).status_code==409
    returned=client.post(f"/api/intelligence/tasks/{task['id']}/transition",headers=headers(alice),json={'version':3,'action':'RETURN','note':'补充'})
    assert returned.json()['status']=='RETURNED' and returned.json()['version']==4
    again=client.post(url,headers=headers(alice),json={'version':4,'assignee_id':alice_id,'reason':'继续核查'})
    assert again.json()['assignee_id']==alice_id and again.json()['status']=='RETURNED'
    second={'version':5,'action':'SUBMIT','result':'CONTINUE','note':'补充核查'}
    assert client.post(f"/api/intelligence/tasks/{task['id']}/transition",headers=headers(handler),json=second).status_code==403
    assert client.post(f"/api/intelligence/tasks/{task['id']}/transition",headers=headers(alice),json=second).status_code==200
    assert client.post(f"/api/intelligence/tasks/{task['id']}/transition",headers=headers(handler),json={'version':6,'action':'CLOSE','note':'复核完成'}).status_code==200
    assert client.post(url,headers=headers(alice),json={'version':7,'assignee_id':new_id,'reason':'关闭后不能分派'}).status_code==409
    assert client.get('/api/intelligence/tasks/mine',headers=alice).json()['total']==0
    with factory() as db:
        events=db.scalars(select(IntelligenceEvent).where(IntelligenceEvent.task_id==task['id'],IntelligenceEvent.action=='REASSIGN')).all()
        assert len(events)==2


def test_reassign_audit_failure_rolls_back(context):
    client,factory=context
    new_id=create_person(factory,'handler','A')
    alice,alice_id,cid,task=seed_task(client,factory)
    engine=factory.kw['bind']
    with engine.begin() as db:
        db.execute(text("CREATE TRIGGER fail_reassign_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'INVESTIGATION_REASSIGN' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    url=f"/api/intelligence/tasks/{task['id']}/reassign"
    body={'version':1,'assignee_id':new_id,'reason':'虚构交接'};same=headers(alice)
    with TestClient(app,raise_server_exceptions=False) as safe:
        assert safe.post(url,headers=same,json=body).status_code==500
    with engine.begin() as db: db.execute(text('DROP TRIGGER fail_reassign_audit'))
    with factory() as db:
        current=db.get(InvestigationTask,task['id'])
        assert (current.assignee_id,current.version)==(alice_id,1)
        assert db.scalars(select(IntelligenceEvent).where(IntelligenceEvent.action=='REASSIGN')).all()==[]
    assert client.post(url,headers=same,json=body).status_code==200
