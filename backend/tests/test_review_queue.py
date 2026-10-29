from sqlalchemy import select
from wellspring.models import User
from wellspring.security import password_hash
from test_workflow import context, auth, headers


def test_review_queue_scope_and_excludes_submitter(context):
    client,factory=context
    with factory() as db:
        alice=db.scalar(select(User).where(User.username=='alice'))
        alice_id=alice.id
        db.add(User(username='reviewer',org_id=alice.org_id,password_hash=password_hash('test-password-123')));db.commit()
    a,r,b=auth(client,'alice'),auth(client,'reviewer'),auth(client,'bob')
    clue=client.post('/api/intelligence/clues',headers=headers(a),json={'title':'虚构','source':'虚构','summary':'虚构'}).json()
    cid=clue['id'];client.post(f'/api/intelligence/clues/{cid}/review',headers=headers(a),json={'version':1,'note':'测试'})
    task=client.post(f'/api/intelligence/clues/{cid}/tasks',headers=headers(a),json={'clue_version':2,'objective':'测试','assignee_id':alice_id}).json()
    assert client.get('/api/intelligence/tasks/reviewable').status_code==401
    assert client.get('/api/intelligence/tasks/reviewable',headers=r).json()['total']==0
    assert client.post(f"/api/intelligence/tasks/{task['id']}/transition",headers=headers(a),json={'version':1,'action':'SUBMIT','note':'测试','result':'NO_FINDING'}).status_code==200
    assert client.get('/api/intelligence/tasks/reviewable',headers=a).json()['total']==0
    assert client.get('/api/intelligence/tasks/reviewable',headers=b).json()['total']==0
    queue=client.get('/api/intelligence/tasks/reviewable',headers=r).json()
    assert queue['total']==1 and queue['items'][0]['clue_id']==cid
    assert 'objective' not in queue['items'][0] and 'result' not in queue['items'][0]
    assert client.post(f"/api/intelligence/tasks/{task['id']}/transition",headers=headers(r),json={'version':2,'action':'RETURN','note':'补充'}).status_code==200
    assert client.get('/api/intelligence/tasks/reviewable',headers=r).json()['total']==0
