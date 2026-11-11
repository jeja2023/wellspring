from uuid import uuid4
from sqlalchemy import select,text
from fastapi.testclient import TestClient
from wellspring.models import User,Organization
from wellspring.access_policy import CODES,route_permissions
from wellspring.main import app
from test_workflow import context,auth,headers


def root(context):
    client,factory=context
    with factory() as db:
        actor=db.scalar(select(User).where(User.username=='alice'));actor.is_admin=True;db.commit();org=actor.org_id
    return client,factory,auth(client,'alice'),org


def role(client,actor,permissions=None,kind='USER'):
    response=client.post('/api/system/roles',headers=headers(actor),json={'code':'test_'+uuid4().hex,'name':'合成角色','kind':kind,'permissions':permissions if permissions is not None else ['cases.read','audit.read']})
    assert response.status_code==201,response.text
    return response.json()


def create(client,actor,org,role_id,name='newuser',**values):
    return client.post('/api/system/users',headers=headers(actor),json={'username':name,'password':'synthetic-password-123','org_id':org,'role_id':role_id,**values})


def login(client,name='newuser',password='synthetic-password-123'):
    response=client.post('/api/login',json={'username':name,'password':password});assert response.status_code==200,response.text
    return {'Authorization':'Bearer '+response.json()['token']}


def test_created_role_enforces_read_write_import_and_unknown_permissions(context):
    client,_,a,org=root(context);r=role(client,a)
    assert create(client,a,org,r['id']).status_code==201
    h=login(client)
    assert client.get('/api/cases',headers=h).status_code==200
    assert client.post('/api/cases',headers=headers(h),json={'number':'NO','title':'x'}).status_code==403
    assert client.post('/api/imports/case-batches',headers=headers(h),json={'source':'x','content':'案件编号,案件名称\nA,B'}).status_code==403
    assert client.get('/api/system/options',headers=h).status_code==403
    assert client.post('/api/case-information/search',headers=h,json={}).status_code==403
    assert client.get('/api/wastewater/results/x/events',headers=h).status_code==403
    assert client.post('/api/system/roles',headers=headers(a),json={'code':'unknown','name':'错误','permissions':['cases.superpower']}).status_code==422
    assert client.post('/api/system/roles',headers=headers(a),json={'code':'admin_priv','name':'错误','permissions':['system.users']}).status_code==422


def test_delegated_admin_only_manages_own_regular_accounts(context):
    client,factory,a,org=root(context)
    low=role(client,a);high=role(client,a,['cases.read','cases.write']);manager=role(client,a,['system.users','cases.read','audit.read'],'ADMIN')
    assert create(client,a,org,manager['id'],'manager').status_code==201
    h=login(client,'manager')
    assert create(client,h,org,low['id'],'managed').status_code==201
    assert create(client,h,org,high['id'],'escalate').status_code==403
    assert create(client,h,org,low['id'],'super',is_admin=True).status_code==403
    with factory() as db:other=db.scalar(select(Organization).where(Organization.name=='B')).id
    assert create(client,h,other,low['id'],'other-org').status_code==403
    assert client.post('/api/system/roles/search',headers=h,json={}).status_code==403
    assert client.post('/api/system/organizations/search',headers=h,json={}).status_code==403
    listed=client.post('/api/system/users/search',headers=h,json={}).json()['items']
    names=[u['username'] for u in listed]
    assert 'managed' in names and 'alice' not in names and 'manager' not in names


def test_user_update_revokes_sessions_and_preserves_last_superadmin(context):
    client,factory,a,org=root(context);r=role(client,a)
    created=create(client,a,org,r['id']).json();h=login(client)
    body={'version':1,'org_id':org,'role_id':r['id'],'active':False}
    assert client.post(f"/api/system/users/{created['id']}/update",headers=headers(a),json=body).status_code==200
    assert client.get('/api/session',headers=h).status_code==401
    assert client.post('/api/login',json={'username':'newuser','password':'synthetic-password-123'}).status_code==401
    assert client.post(f"/api/system/users/{created['id']}/update",headers=headers(a),json=body).status_code==409
    with factory() as db:identity=db.scalar(select(User.id).where(User.username=='alice'))
    assert client.post(f'/api/system/users/{identity}/update',headers=headers(a),json={'version':1,'org_id':org,'role_id':r['id'],'active':False,'is_admin':False}).json()['code']=='LAST_ADMIN'


def test_password_reset_requires_new_login_and_replays_safely(context):
    client,_,a,org=root(context);r=role(client,a);u=create(client,a,org,r['id']).json();h=login(client)
    key=headers(a);body={'version':1,'password':'new-password-12345'}
    result=client.post(f"/api/system/users/{u['id']}/password",headers=key,json=body)
    assert result.status_code==200 and 'password' not in result.text
    assert client.post(f"/api/system/users/{u['id']}/password",headers=key,json=body).json()==result.json()
    assert client.get('/api/session',headers=h).status_code==401
    login(client,password='new-password-12345')


def test_role_change_revokes_and_rechecks_effective_permissions(context):
    client,_,a,org=root(context);r=role(client,a,['cases.read','cases.write']);create(client,a,org,r['id']);h=login(client)
    response=client.post(f"/api/system/roles/{r['id']}/update",headers=headers(a),json={'version':1,'name':r['name'],'kind':'USER','permissions':['audit.read'],'active':True})
    assert response.status_code==200
    assert client.get('/api/session',headers=h).status_code==401
    h=login(client)
    assert client.get('/api/cases',headers=h).status_code==403
    assert client.get('/api/audit/mine',headers=h).status_code==200


def test_organization_cycle_in_use_and_disabled_login(context):
    client,factory,a,org=root(context)
    parent=client.post('/api/system/organizations',headers=headers(a),json={'name':'合成上级'}).json()
    child=client.post('/api/system/organizations',headers=headers(a),json={'name':'合成下级','parent_id':parent['id']}).json()
    assert client.post(f"/api/system/organizations/{parent['id']}/update",headers=headers(a),json={'version':1,'name':parent['name'],'parent_id':child['id']}).json()['code']=='ORGANIZATION_CYCLE'
    assert client.post(f"/api/system/organizations/{parent['id']}/update",headers=headers(a),json={'version':1,'name':parent['name'],'active':False}).json()['code']=='ORGANIZATION_IN_USE'
    r=role(client,a);create(client,a,child['id'],r['id']);h=login(client)
    assert client.post(f"/api/system/organizations/{child['id']}/update",headers=headers(a),json={'version':1,'name':child['name'],'active':False}).status_code==409
    with factory() as db:db.get(Organization,child['id']).active=False;db.commit()
    assert client.get('/api/session',headers=h).status_code==401


def test_authorization_changes_roll_back_with_audit_failure(context):
    client,factory,a,org=root(context);r=role(client,a);u=create(client,a,org,r['id']).json();h=login(client)
    with factory.kw['bind'].begin() as db:db.execute(text("CREATE TRIGGER fail_user_audit BEFORE INSERT ON audit_events WHEN NEW.action='USER_UPDATE' BEGIN SELECT RAISE(ABORT,'synthetic'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe:
        assert safe.post(f"/api/system/users/{u['id']}/update",headers=headers(a),json={'version':1,'org_id':org,'role_id':r['id'],'active':False}).status_code==500
    assert client.get('/api/session',headers=h).status_code==200
    with factory() as db:assert db.get(User,u['id']).active is True and db.get(User,u['id']).version==1


def test_all_business_routes_map_to_registered_permissions():
    schema=TestClient(app).get('/openapi.json').json()
    for path,operations in schema['paths'].items():
        if path in {'/api/login','/api/ready','/api/health'}:continue
        for method in operations:assert route_permissions(method.upper(),path)<=CODES,(method,path)


def test_self_password_change_revokes_all_sessions(context):
    client,_,a,org=root(context);r=role(client,a);create(client,a,org,r['id']);h=login(client)
    assert client.post('/api/account/password',headers=h,json={'old_password':'wrong','password':'new-password-12345'}).status_code==403
    assert client.post('/api/account/password',headers=h,json={'old_password':'synthetic-password-123','password':'new-password-12345'}).status_code==200
    assert client.get('/api/session',headers=h).status_code==401
    login(client,password='new-password-12345')


def test_builtin_role_changes_do_not_revoke_superadministrator(context):
    client,factory,a,org=root(context)
    from wellspring.access_policy import DEFAULT_ROLE_ID
    from wellspring.access_models import Role
    with factory() as db:r=db.get(Role,DEFAULT_ROLE_ID);version=r.version
    response=client.post(f'/api/system/roles/{DEFAULT_ROLE_ID}/update',headers=headers(a),json={'version':version,'name':'业务用户','kind':'USER','permissions':['cases.read'],'active':False})
    assert response.status_code==200
    assert client.get('/api/session',headers=a).status_code==200
