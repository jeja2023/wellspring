from datetime import date
import json
from uuid import uuid4
import pytest
from sqlalchemy import func,select,text
from fastapi.testclient import TestClient
from wellspring.models import Clue,Organization,User,ClueImportBatch,IdempotencyRecord
from wellspring.intelligence_models import ClueDelivery,DeliveryEvent
from wellspring.security import password_hash
from wellspring.main import app
from test_workflow import context,auth,headers


def hierarchy(context):
    client,factory=context
    with factory() as db:
        city=db.scalar(select(Organization).where(Organization.name=='A'));city.unit_type='CITY'
        brigade=db.scalar(select(Organization).where(Organization.name=='B'));brigade.unit_type='BRANCH';brigade.parent_id=city.id
        station=Organization(name='合成派出所',unit_type='STATION',parent_id=brigade.id)
        other=Organization(name='无关单位',unit_type='BRANCH');db.add_all([station,other]);db.flush()
        db.add(User(username='station',org_id=station.id,password_hash=password_hash('test-password-123')))
        db.add(User(username='unrelated',org_id=other.id,password_hash=password_hash('test-password-123')));db.commit()
        ids={'city':city.id,'brigade':brigade.id,'station':station.id,'other':other.id}
    return client,factory,ids,{name:auth(client,user) for name,user in [('city','alice'),('brigade','bob'),('station','station'),('other','unrelated')]}


def clue(client,actor,priority='NORMAL'):
    created=client.post('/api/intelligence/clues',headers=headers(actor),json={'title':'合成层级线索','summary':'仅合成资料','source':'合成来源','priority':priority}).json()
    response=client.post(f"/api/intelligence/clues/{created['id']}/review",headers=headers(actor),json={'version':1,'note':'合成核验'})
    assert response.status_code==200,response.text
    return response.json()


def post(client,actor,path,body):
    response=client.post('/api/intelligence/'+path,headers=headers(actor),json=body)
    assert response.status_code in (200,201),response.text
    return response.json()


def test_city_brigade_station_feedback_and_return_closed_loop(context):
    client,factory,ids,actors=hierarchy(context);source=clue(client,actors['city'])
    root=post(client,actors['city'],f"clues/{source['id']}/dispatch",{'version':2,'recipient_org_id':ids['brigade'],'objective':'分局大队组织核查','allow_station':True,'due_date':'2030-01-10'})
    assert client.get(f"/api/intelligence/deliveries/{root['id']}",headers=actors['other']).status_code==404
    root=post(client,actors['brigade'],f"deliveries/{root['id']}/accept",{'version':1})
    assert root['status']=='PROCESSING'
    child=post(client,actors['brigade'],f"deliveries/{root['id']}/dispatch",{'version':root['version'],'recipient_org_id':ids['station'],'objective':'派出所现场核查','allow_station':True,'due_date':'2030-01-09'})
    response=client.post(f"/api/intelligence/deliveries/{root['id']}/feedback",headers=headers(actors['brigade']),json={'version':3,'disposition':'核查','feedback':'尚有下级','result':'CONTINUE'})
    assert response.status_code==409 and response.json()['code']=='CHILDREN_PENDING'
    child=post(client,actors['station'],f"deliveries/{child['id']}/accept",{'version':1})
    child=post(client,actors['station'],f"deliveries/{child['id']}/progress",{'version':child['version'],'note':'已开展合成核查'})
    child=post(client,actors['station'],f"deliveries/{child['id']}/feedback",{'version':child['version'],'disposition':'已核查合成场所','feedback':'合成结论一','result':'NO_FINDING'})
    child=post(client,actors['brigade'],f"deliveries/{child['id']}/resolve",{'version':child['version'],'action':'RETURN','note':'请补充依据'})
    child=post(client,actors['station'],f"deliveries/{child['id']}/feedback",{'version':child['version'],'disposition':'已补充核查','feedback':'合成结论二及依据','result':'VERIFIED'})
    child=post(client,actors['brigade'],f"deliveries/{child['id']}/resolve",{'version':child['version'],'action':'CLOSE','note':'依据齐全'})
    root=post(client,actors['brigade'],f"deliveries/{root['id']}/feedback",{'version':3,'disposition':'汇总派出所核查','feedback':'汇总反馈及复核意见','result':'VERIFIED'})
    root=post(client,actors['city'],f"deliveries/{root['id']}/resolve",{'version':root['version'],'action':'CLOSE','note':'支队复核办结'})
    assert root['status']=='CLOSED'
    history=client.get(f"/api/intelligence/deliveries/{child['id']}",headers=actors['city']).json()
    assert len([item for item in history['events']['items'] if item['action']=='FEEDBACK'])==2
    assert history['events']['items'][-1]['action']=='CLOSE'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ClueDelivery).where(ClueDelivery.status=='CLOSED'))==2


def test_important_and_inherited_station_restriction_cannot_be_bypassed(context):
    client,_,ids,actors=hierarchy(context);source=clue(client,actors['city'],'IMPORTANT')
    route=f"/api/intelligence/clues/{source['id']}/dispatch"
    response=client.post(route,headers=headers(actors['city']),json={'version':2,'recipient_org_id':ids['brigade'],'objective':'核查','allow_station':True})
    assert response.status_code==403
    root=post(client,actors['city'],f"clues/{source['id']}/dispatch",{'version':2,'recipient_org_id':ids['brigade'],'objective':'仅大队承办'})
    root=post(client,actors['brigade'],f"deliveries/{root['id']}/accept",{'version':1})
    for allow in [False,True]:
        response=client.post(f"/api/intelligence/deliveries/{root['id']}/dispatch",headers=headers(actors['brigade']),json={'version':root['version'],'recipient_org_id':ids['station'],'objective':'尝试绕过限制','allow_station':allow})
        assert response.status_code==403
    assert client.get(f"/api/intelligence/deliveries/{root['id']}",headers=actors['station']).status_code==404
    options=client.get('/api/intelligence/delivery-options?parent_id='+root['id'],headers=actors['brigade']).json()
    assert ids['station'] not in [item['id'] for item in options['organizations']]


def test_dispatch_bounds_idempotency_accept_version_and_snapshot(context):
    client,factory,ids,actors=hierarchy(context);source=clue(client,actors['city'])
    route=f"/api/intelligence/clues/{source['id']}/dispatch";body={'version':2,'recipient_org_id':ids['brigade'],'objective':'核查'};key=headers(actors['city'])
    first=client.post(route,headers=key,json=body);assert first.status_code==201
    assert client.post(route,headers=key,json=body).json()['id']==first.json()['id']
    assert client.post(route,headers=headers(actors['city']),json={**body,'version':3}).status_code==409
    assert client.post(route,headers=headers(actors['city']),json={**body,'version':3,'recipient_org_id':ids['other']}).status_code==403
    assert client.post(route,headers=headers(actors['city']),json={**body,'version':3,'recipient_org_id':ids['station'],'allow_station':True}).status_code==403
    identity=first.json()['id'];key=headers(actors['brigade'])
    accepted=client.post(f'/api/intelligence/deliveries/{identity}/accept',headers=key,json={'version':1})
    assert accepted.status_code==200
    assert client.post(f'/api/intelligence/deliveries/{identity}/accept',headers=key,json={'version':1}).status_code==200
    assert client.post(f'/api/intelligence/deliveries/{identity}/accept',headers=headers(actors['brigade']),json={'version':1}).status_code==409
    with factory() as db:
        row=db.get(Clue,source['id']);row.summary='后续原文更正';db.commit()
    assert client.get(f'/api/intelligence/deliveries/{identity}',headers=actors['brigade']).json()['delivery']['snapshot']['summary']=='仅合成资料'


def test_clue_import_preview_atomicity_and_no_overwrite(context):
    client,factory,_,actors=hierarchy(context)
    body={'filename':'synthetic.xlsx','rows':[{'row_number':2,'reference_no':'EX-1','title':'合成导入','summary':'原文','source':'合成','priority':'IMPORTANT'}]}
    preview=client.post('/api/intelligence/imports/preview',headers=actors['city'],json=body)
    assert preview.status_code==200 and preview.json()['valid_count']==1
    key=headers(actors['city']);response=client.post('/api/intelligence/imports/confirm',headers=key,json=body)
    assert response.status_code==201,response.text
    assert client.post('/api/intelligence/imports/confirm',headers=key,json=body).json()['id']==response.json()['id']
    assert client.post('/api/intelligence/imports/preview',headers=actors['city'],json=body).json()['invalid_count']==1
    assert client.post('/api/intelligence/imports/confirm',headers=headers(actors['city']),json=body).status_code==422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Clue))==1
        assert db.scalar(select(func.count()).select_from(ClueImportBatch))==1


def test_recipient_can_reassign_to_authorized_colleague_and_old_handler_cannot_submit(context):
    client,factory,ids,actors=hierarchy(context);source=clue(client,actors['city'])
    with factory() as db:
        person=User(username='brigade-colleague',org_id=ids['brigade'],password_hash=password_hash('test-password-123'));db.add(person);db.commit();person_id=person.id
    row=post(client,actors['city'],f"clues/{source['id']}/dispatch",{'version':2,'recipient_org_id':ids['brigade'],'objective':'合成核查'})
    row=post(client,actors['brigade'],f"deliveries/{row['id']}/accept",{'version':1})
    row=post(client,actors['brigade'],f"deliveries/{row['id']}/reassign",{'version':row['version'],'assignee_id':person_id,'note':'合成转交'})
    assert row['assignee_id']==person_id
    body={'version':row['version'],'disposition':'合成处置','feedback':'合成反馈','result':'NO_FINDING'}
    assert client.post(f"/api/intelligence/deliveries/{row['id']}/feedback",headers=headers(actors['brigade']),json=body).status_code==403
    assert client.post(f"/api/intelligence/deliveries/{row['id']}/feedback",headers=headers(auth(client,'brigade-colleague')),json=body).status_code==200


def test_active_flow_blocks_organization_reparenting_and_feedback_audit_failure_rolls_back(context):
    client,factory,ids,actors=hierarchy(context);source=clue(client,actors['city'])
    row=post(client,actors['city'],f"clues/{source['id']}/dispatch",{'version':2,'recipient_org_id':ids['brigade'],'objective':'合成核查'})
    row=post(client,actors['brigade'],f"deliveries/{row['id']}/accept",{'version':1})
    with factory() as db:
        actor=db.scalar(select(User).where(User.username=='alice'));actor.is_admin=True;db.commit()
        org=db.get(Organization,ids['brigade']);body={'version':org.version,'name':org.name,'parent_id':None,'unit_type':'BRANCH'}
    assert client.post('/api/system/organizations/'+ids['brigade']+'/update',headers=headers(actors['city']),json=body).status_code==409
    engine=factory.kw['bind']
    with engine.begin() as connection:connection.execute(text("CREATE TRIGGER reject_flow_audit BEFORE INSERT ON audit_events WHEN NEW.action='DELIVERY_FEEDBACK' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe:
        response=safe.post(f"/api/intelligence/deliveries/{row['id']}/feedback",headers=headers(actors['brigade']),json={'version':row['version'],'disposition':'处置','feedback':'反馈','result':'NO_FINDING'})
        assert response.status_code==500
    with engine.begin() as connection:connection.execute(text('DROP TRIGGER reject_flow_audit'))
    with factory() as db:
        assert db.get(ClueDelivery,row['id']).status=='PROCESSING'
        assert db.scalar(select(func.count()).select_from(DeliveryEvent).where(DeliveryEvent.delivery_id==row['id'],DeliveryEvent.action=='FEEDBACK'))==0
