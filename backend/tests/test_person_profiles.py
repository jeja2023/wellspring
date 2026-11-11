from datetime import date,timedelta
import json
from uuid import uuid4
import pytest
from sqlalchemy import func,select,text
from fastapi.testclient import TestClient
from wellspring.main import app
from wellspring.models import Case,PersonDraft,Organization,User
from wellspring.person_models import PersonRecord,PersonEvent,PersonTask,PersonTransfer
from wellspring.access_models import Role
from wellspring.access_policy import CODES
from wellspring.security import password_hash
from wellspring.person_core import today
from test_workflow import context,auth,headers


def prepare(context):
    client,factory=context
    with factory() as db:
        first=db.scalar(select(User).where(User.username=='alice'));first.is_admin=True
        second=User(username='person-reviewer',org_id=first.org_id,password_hash=password_hash('test-password-123'),is_admin=True);db.add(second)
        other=db.scalar(select(User).where(User.username=='bob'));other.is_admin=True;db.commit()
        organizations={'source':first.org_id,'target':other.org_id}
    return client,factory,auth(client,'alice'),auth(client,'person-reviewer'),auth(client,'bob'),organizations


def post(client,actor,path,body):
    response=client.post('/api/person-drafts'+path,headers=headers(actor),json=body)
    assert response.status_code in {200,201},response.text
    return response.json()


def person(client,actor,reviewer):
    row=post(client,actor,'',{'name':'合成同名人员','source':'合成资料','document_type':'OTHER','document_number':'SYNTHETIC-'+uuid4().hex[:10],'phone':'00000000000','address':'合成地址'})
    row=post(client,reviewer,'/'+row['id']+'/identity-review',{'version':row['version'],'action':'CONFIRM','note':'核对合成身份依据','document_no':'SYNTHETIC-ID-REVIEW'})
    return row


def record(client,actor,profile,kind='MEASURE',record_type='COMMUNITY',details=None,**extra):
    profile=client.get('/api/person-drafts/'+profile['id'],headers=actor).json()
    return post(client,actor,'/'+profile['id']+'/records',{'person_version':profile['version'],'kind':kind,'record_type':record_type,'occurred_on':str(today()-timedelta(days=30)),
        'source':'合成材料','document_no':'SYNTHETIC-DECISION','basis':'合成来源及核对依据','details':details if details is not None else {'decision_org':'合成决定机关','execution_agency':'合成街道执行机构','report_due_on':str(today()-timedelta(days=20))},**extra})


def verify(client,actor,row):return post(client,actor,'/records/'+row['id']+'/review',{'version':row['version'],'action':'CONFIRM','document_no':'SYNTHETIC-REVIEW','note':'核对合成业务依据'})


def test_person_identity_independent_review_duplicates_and_redaction(context):
    client,factory,a,r,b,_=prepare(context)
    body={'name':'合成同名','source':'合成','document_type':'OTHER','document_number':'SYNTHETIC-IDENTITY-01','phone':'SYNTHETIC-PHONE','address':'SYNTHETIC-ADDRESS'}
    created=post(client,a,'',body)
    assert 'document_number' not in created and 'phone' not in created
    response=client.post('/api/person-drafts/'+created['id']+'/identity-review',headers=headers(a),json={'version':1,'action':'CONFIRM','note':'尝试自审','document_no':'x'})
    assert response.status_code==403 and response.json()['code']=='SELF_REVIEW'
    assert client.post('/api/person-drafts',headers=headers(a),json=body).status_code==409
    same_name=post(client,a,'',{'name':'合成同名','source':'另一来源'});assert same_name['id']!=created['id']
    verified=post(client,r,'/'+created['id']+'/identity-review',{'version':1,'action':'CONFIRM','note':'已核对资料','document_no':'合成文号'})
    assert verified['verification_status']=='VERIFIED'
    with factory() as db:
        user=db.scalar(select(User).where(User.username=='person-reviewer'));user.is_admin=False
        role=Role(code='person_read_'+uuid4().hex[:8],name='普通人员查询',permissions_json=json.dumps(['persons.read']));db.add(role);db.flush();user.role_id=role.id;db.commit()
    detail=client.get('/api/person-drafts/'+created['id'],headers=r)
    assert detail.status_code==200
    assert all(value not in detail.text for value in ['SYNTHETIC-IDENTITY-01','SYNTHETIC-PHONE','SYNTHETIC-ADDRESS'])
    assert detail.json()['case_count'] is None and detail.json()['use_count'] is None
    assert client.post('/api/person-drafts/search',headers=r,json={'view':'treatment'}).status_code==403
    assert client.get('/api/person-drafts/'+created['id'],headers=b).status_code==404


def test_measure_episode_execution_due_reminders_and_no_automatic_release(context):
    client,factory,a,r,_,_=prepare(context);profile=person(client,a,r)
    row=record(client,a,profile,expected_end_on=str(today()-timedelta(days=1)))
    assert client.post('/api/person-drafts/records/'+row['id']+'/review',headers=headers(a),json={'version':1,'action':'CONFIRM','note':'自核','document_no':'x'}).status_code==403
    row=verify(client,r,row)
    assert row['state']=='DECIDED'
    profile=client.get('/api/person-drafts/'+profile['id'],headers=a).json()
    assert profile['current_measures'][0]['needs_end_check'] and profile['task_count']==2
    assert client.post('/api/person-drafts/records/'+row['id']+'/execute',headers=headers(a),json={'version':row['version'],'action':'ADMIT','occurred_on':str(today()-timedelta(days=20)),'note':'错误动作','document_no':'x'}).status_code==422
    row=post(client,a,'/records/'+row['id']+'/execute',{'version':row['version'],'action':'REPORT','occurred_on':str(today()-timedelta(days=20)),'note':'合成实际报到','document_no':'SYNTHETIC-REPORT'})
    assert row['state']=='ACTIVE'
    tasks=client.get('/api/person-drafts/'+profile['id']+'/tasks',headers=a).json()['items']
    end_task=next(item for item in tasks if item['task_type']=='END_CHECK')
    post(client,a,'/tasks/'+end_task['id']+'/complete',{'version':end_task['version'],'action':'DONE','note':'到期已核对，尚无解除文书'})
    with factory() as db:assert db.get(PersonRecord,row['id']).state=='ACTIVE'
    row=post(client,a,'/records/'+row['id']+'/execute',{'version':row['version'],'action':'RELEASE','occurred_on':str(today()),'note':'依据合成解除文书登记','document_no':'SYNTHETIC-RELEASE'})
    assert row['state']=='ENDED' and row['actual_end_on']==str(today())
    assert not client.get('/api/person-drafts/'+profile['id'],headers=a).json()['current_measures']


def test_case_role_and_drug_records_can_overlap_without_reclassifying_identity(context):
    client,factory,a,r,_,_=prepare(context);profile=person(client,a,r)
    case=client.post('/api/cases',headers=headers(a),json={'number':'SYNTHETIC-CASE','title':'合成案件'}).json()
    case_record=record(client,a,profile,'CASE','SUSPECT',{'case_nature':'CRIMINAL','stage':'INVESTIGATION','allegation':'合成涉嫌事项'},case_id=case['id'])
    verify(client,r,case_record)
    use=record(client,a,profile,'USE','REPORTED',{'finding':'合成待核实报告'});verify(client,r,use)
    assert client.post('/api/person-drafts/search',headers=a,json={'view':'case'}).json()['total']==1
    current=client.get('/api/person-drafts/'+profile['id'],headers=a).json();assert current['case_count']==1 and current['use_count']==1 and not current['current_measures']
    invalid={'person_version':current['version'],'kind':'CASE','record_type':'CONVICTED','occurred_on':str(today()),'source':'合成','document_no':'x','basis':'x','case_id':case['id'],'details':{'stage':'INVESTIGATION'}}
    assert client.post('/api/person-drafts/'+profile['id']+'/records',headers=headers(a),json=invalid).status_code==422
    replacement=record(client,a,profile,'CASE','DEFENDANT',{'case_nature':'CRIMINAL','stage':'TRIAL','allegation':'合成起诉事项'},case_id=case['id'],replaces_id=case_record['id'])
    verify(client,r,replacement)
    with factory() as db:assert db.get(PersonRecord,case_record['id']).verification_status=='SUPERSEDED'
    assert client.get('/api/person-drafts/'+profile['id'],headers=a).json()['case_count']==1


def test_transfer_reception_grants_current_measures_not_all_criminal_or_health_history(context):
    client,factory,a,r,b,orgs=prepare(context);profile=person(client,a,r)
    measure=verify(client,r,record(client,a,profile))
    private=verify(client,r,record(client,a,profile,'TEST','LAB',{'method':'合成方法','laboratory':'合成实验室','result':'NEGATIVE'}))
    profile=client.get('/api/person-drafts/'+profile['id'],headers=a).json()
    transfer=post(client,a,'/'+profile['id']+'/transfers',{'person_version':profile['version'],'target_org_id':orgs['target'],'reason':'合成管辖交接'})
    assert client.get('/api/person-drafts/'+profile['id'],headers=b).status_code==404
    inbox=client.get('/api/person-drafts/transfers/inbox',headers=b).json()
    assert inbox['total']==1 and 'details' not in inbox['items'][0]
    key=headers(b);body={'version':1,'action':'ACCEPT','note':'合成接收确认'}
    response=client.post('/api/person-drafts/transfers/'+transfer['id']+'/resolve',headers=key,json=body)
    assert response.status_code==200,response.text
    assert client.post('/api/person-drafts/transfers/'+transfer['id']+'/resolve',headers=key,json=body).json()==response.json()
    received=client.get('/api/person-drafts/'+profile['id'],headers=b).json()
    assert received['responsible_org_id']==orgs['target'] and received['id']==profile['id']
    records=client.get('/api/person-drafts/'+profile['id']+'/records',headers=b).json()['items']
    assert [row['id'] for row in records]==[measure['id']] and private['id'] not in [row['id'] for row in records]
    with factory() as db:assert db.get(PersonRecord,measure['id']).manager_org_id==orgs['target']
    assert client.post('/api/person-drafts/'+profile['id']+'/update',headers=headers(a),json={'version':received['version'],'name':'试图跨责任修改','source':'x'}).status_code==403


def test_sensitive_permissions_cannot_be_bypassed_by_direct_record_posts(context):
    client,factory,a,r,_,_=prepare(context);profile=person(client,a,r)
    with factory() as db:
        user=db.scalar(select(User).where(User.username=='person-reviewer'));user.is_admin=False
        role=Role(code='limited_'+uuid4().hex[:8],name='仅人员维护',permissions_json=json.dumps(['persons.read','persons.write']));db.add(role);db.flush();user.role_id=role.id;db.commit()
    response=client.post('/api/person-drafts/'+profile['id']+'/records',headers=headers(r),json={'person_version':profile['version'],'kind':'MEASURE','record_type':'COMMUNITY','occurred_on':str(today()),'source':'x','document_no':'x','basis':'x','details':{'decision_org':'x','execution_agency':'x'}})
    assert response.status_code==403
    assert client.get('/api/person-drafts/'+profile['id']+'/records?kind=MEASURE',headers=r).status_code==403
    assert client.post('/api/person-drafts',headers=headers(r),json={'name':'x','source':'x','document_type':'OTHER','document_number':'HIDDEN-KEY'}).status_code==403


def test_record_review_audit_failure_rolls_back_state_and_tasks(context):
    client,factory,a,r,_,_=prepare(context);profile=person(client,a,r);row=record(client,a,profile,expected_end_on=str(today()+timedelta(days=10)))
    engine=factory.kw['bind']
    with engine.begin() as db:db.execute(text("CREATE TRIGGER reject_person_record_audit BEFORE INSERT ON audit_events WHEN NEW.action='PERSON_RECORD_REVIEW' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe:
        response=safe.post('/api/person-drafts/records/'+row['id']+'/review',headers=headers(r),json={'version':1,'action':'CONFIRM','note':'合成核对','document_no':'x'})
        assert response.status_code==500
    with engine.begin() as db:db.execute(text('DROP TRIGGER reject_person_record_audit'))
    with factory() as db:
        assert db.get(PersonRecord,row['id']).verification_status=='PENDING'
        assert db.scalar(select(func.count()).select_from(PersonTask))==0


def test_returned_record_can_be_supplemented_and_editor_cannot_self_verify(context):
    client,factory,a,r,_,_=prepare(context);profile=person(client,a,r)
    row=record(client,a,profile,'FOLLOWUP','VISIT',{'content':'合成初次随访'})
    post(client,r,'/records/'+row['id']+'/review',{'version':1,'action':'RETURN','note':'补充依据','document_no':'SYNTHETIC-RETURN'})
    current=client.get('/api/person-drafts/'+profile['id'],headers=a).json()
    updated=post(client,a,'/records/'+row['id']+'/update',{'version':2,'person_version':current['version'],'kind':'FOLLOWUP','record_type':'VISIT','occurred_on':str(today()),'source':'合成来源','document_no':'SYNTHETIC-FOLLOWUP','basis':'已补充核对依据','details':{'content':'补充后的合成随访'}})
    assert updated['verification_status']=='PENDING' and updated['version']==3
    assert client.post('/api/person-drafts/records/'+row['id']+'/review',headers=headers(a),json={'version':3,'action':'CONFIRM','note':'自核尝试','document_no':'x'}).status_code==403
    assert verify(client,r,updated)['verification_status']=='VERIFIED'
    history=client.get('/api/person-drafts/'+profile['id']+'/history',headers=a).json()['items']
    assert any(item['action']=='RECORD_UPDATED' and item['payload']['before']['details']['content']=='合成初次随访' for item in history)


def test_transfer_audit_failure_preserves_responsibility_and_access(context):
    client,factory,a,r,b,orgs=prepare(context);profile=person(client,a,r)
    transfer=post(client,a,'/'+profile['id']+'/transfers',{'person_version':profile['version'],'target_org_id':orgs['target'],'reason':'合成交接'})
    engine=factory.kw['bind']
    with engine.begin() as db:db.execute(text("CREATE TRIGGER reject_person_transfer_audit BEFORE INSERT ON audit_events WHEN NEW.action='PERSON_TRANSFER_RESOLVE' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe:
        assert safe.post('/api/person-drafts/transfers/'+transfer['id']+'/resolve',headers=headers(b),json={'version':1,'action':'ACCEPT','note':'合成接收'}).status_code==500
    with engine.begin() as db:db.execute(text('DROP TRIGGER reject_person_transfer_audit'))
    with factory() as db:
        assert db.get(PersonTransfer,transfer['id']).status=='PENDING'
        assert db.get(PersonDraft,profile['id']).responsible_org_id==orgs['source']
    assert client.get('/api/person-drafts/'+profile['id'],headers=b).status_code==404


def test_identity_mutation_receipts_do_not_replay_full_identifiers_after_privilege_change(context):
    client,factory,a,r,_,_=prepare(context)
    key=headers(a);body={'name':'合成身份重放','source':'合成','document_type':'OTHER','document_number':'SYNTHETIC-REPLAY-SECRET','phone':'SYNTHETIC-PRIVATE-PHONE'}
    response=client.post('/api/person-drafts',headers=key,json=body)
    assert response.status_code==201 and body['document_number'] not in response.text and body['phone'] not in response.text
    with factory() as db:
        user=db.scalar(select(User).where(User.username=='alice'));user.is_admin=False
        role=Role(code='base_'+uuid4().hex[:8],name='基础维护',permissions_json=json.dumps(['persons.read','persons.write']));db.add(role);db.flush();user.role_id=role.id;db.commit()
    assert client.post('/api/person-drafts',headers=key,json=body).status_code==403
