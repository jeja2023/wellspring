from datetime import timedelta
import json
from uuid import uuid4
import pytest
from sqlalchemy import func, select, text
from fastapi.testclient import TestClient
from wellspring.main import app
from wellspring.models import Clue, Organization, User, now
from wellspring.place_models import GeoLocation, GeoLocationEvent, Place, PlaceIncident, PlaceInspection
from wellspring.access_models import Role
from wellspring.security import password_hash
from test_workflow import context, auth, headers


def prepare(context):
    client, factory = context
    with factory() as db:
        actor = db.scalar(select(User).where(User.username == 'alice')); actor.is_admin = True
        other = db.scalar(select(User).where(User.username == 'bob')); other.is_admin = True
        db.add(User(username='place-reviewer', org_id=actor.org_id, password_hash=password_hash('test-password-123'), is_admin=True))
        db.commit()
    return client, factory, auth(client, 'alice'), auth(client, 'place-reviewer'), auth(client, 'bob')


def post(client, actor, path, body, key=None):
    response = client.post('/api' + path, headers=key or headers(actor), json=body)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def place(client, actor):
    return post(client, actor, '/places', {'code': 'SYNTHETIC-'+uuid4().hex[:10], 'name': '合成场所', 'kind': 'APARTMENT',
        'district': '合成区域', 'address': '合成街道', 'responsible': '合成责任岗', 'management_basis': '合成巡查计划'})


def incident(client, actor, place):
    return post(client, actor, '/places/'+place['id']+'/incidents', {'title': '合成现场事件', 'occurred_at': (now()-timedelta(hours=1)).isoformat(),
        'source': '合成巡查', 'facts': '合成现场情况，不涉及真实人员', 'material_ref': 'SYNTHETIC-MATERIAL-01'})


def test_place_incident_independent_review_clue_and_closure(context):
    client, factory, a, r, b = prepare(context)
    p = place(client, a); row = incident(client, a, p)
    path = '/places/incidents/'+row['id']
    assert client.post('/api'+path+'/transition', headers=headers(a), json={'version':1,'action':'CONFIRM','note':'本人核验'}).status_code == 403
    assert client.post('/api'+path+'/clue', headers=headers(a), json={'version':1,'note':'尚未核验'}).status_code == 409
    row = post(client, r, path+'/transition', {'version':1,'action':'RETURN','note':'补充来源'})
    body = {key:row[key] for key in ['title','occurred_at','source','facts','material_ref']}
    row = post(client, a, path+'/update', {'version':row['version'], **body})
    row = post(client, r, path+'/transition', {'version':row['version'],'action':'CONFIRM','note':'已人工核对合成来源'})
    key = headers(a); body = {'version':row['version'],'note':'转录具体事件'}
    row = post(client, a, path+'/clue', body, key)
    assert post(client, a, path+'/clue', body, key) == row
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Clue)) == 1
        assert db.get(Clue,row['clue_id']).status == 'DRAFT'
    row = post(client, a, path+'/transition', {'version':row['version'],'action':'SUBMIT','note':'合成处置结果'})
    assert client.post('/api'+path+'/transition', headers=headers(a), json={'version':row['version'],'action':'CLOSE','note':'自审办结'}).status_code == 403
    row = post(client, r, path+'/transition', {'version':row['version'],'action':'CLOSE','note':'核对后办结'})
    assert row['status'] == 'CLOSED'
    assert client.get('/api/places/'+p['id'], headers=b).status_code == 404
    history = client.get('/api/places/'+p['id']+'/history',headers=a).json()
    assert any(item['action']=='INCIDENT_UPDATED' for item in history['items'])


def test_inspection_deadline_and_audit_failure_roll_back(context):
    client, factory, a, _, _ = prepare(context); p = place(client,a)
    body = {'inspected_on':str(now().date()),'findings':'合成整改事项','requires_action':True,'due_on':str(now().date()+timedelta(days=2))}
    row = post(client,a,'/places/'+p['id']+'/inspections',body)
    engine = factory.kw['bind']
    with engine.begin() as db:
        db.execute(text("CREATE TRIGGER reject_place_audit BEFORE INSERT ON audit_events WHEN NEW.action='PLACE_INSPECTION_COMPLETED' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END"))
    path = '/api/places/inspections/'+row['id']+'/complete'
    with TestClient(app,raise_server_exceptions=False) as safe:
        assert safe.post(path,headers=headers(a),json={'version':1,'note':'合成复查完成'}).status_code == 500
    with factory() as db: assert db.get(PlaceInspection,row['id']).status == 'OPEN'
    with engine.begin() as db: db.execute(text('DROP TRIGGER reject_place_audit'))
    assert post(client,a,path.removeprefix('/api'),{'version':1,'note':'合成复查完成'})['status'] == 'DONE'
    assert client.post('/api/places/'+p['id']+'/inspections',headers=headers(a),json={**body,'due_on':None}).status_code == 422


def test_map_coordinates_scope_versions_clear_and_source_history(context):
    client, factory, a, _, b = prepare(context); p = place(client,a)
    path = '/geography/PLACE/'+p['id']+'/location'
    body = {'version':0,'longitude':116.4,'latitude':39.9,'source':'合成 WGS84 测试坐标'}
    key = headers(a); row = post(client,a,path,body,key)
    assert post(client,a,path,body,key) == row
    assert client.post('/api'+path,headers=headers(a),json=body).status_code == 409
    assert client.post('/api'+path,headers=headers(b),json=body).status_code == 404
    for bad in [{'latitude':None},{'longitude':181},{'coordinate_system':'GCJ02'}]:
        assert client.post('/api'+path,headers=headers(a),json={**body,**bad}).status_code == 422
    mapped = post(client,a,'/geography/points',{'layer':'PLACE','bbox':[116,39,117,40]})
    assert mapped['total'] == 1 and mapped['items'][0]['resource_id'] == p['id']
    assert post(client,b,'/geography/points',{})['total'] == 0
    assert post(client,a,'/geography/points',{'bbox':[100,20,110,30]})['total'] == 0
    post(client,a,path,{'version':1,'source':'移除误标点位','longitude':None,'latitude':None})
    assert post(client,a,'/geography/points',{})['total'] == 0
    assert post(client,a,'/geography/search',{'located':False})['total'] == 1
    assert client.get('/api/geography/PLACE/'+p['id']+'/history',headers=a).json()['total'] == 2
    with factory() as db: assert db.scalar(select(func.count()).select_from(GeoLocationEvent)) == 2


def test_map_requires_module_permissions_and_never_exposes_event_facts(context):
    client, factory, a, r, _ = prepare(context); p = place(client,a); row = incident(client,a,p)
    post(client,a,'/geography/INCIDENT/'+row['id']+'/location',{'version':0,'longitude':110,'latitude':30,'source':'合成来源'})
    response = post(client,a,'/geography/points',{'layer':'INCIDENT'})
    assert response['total'] == 1 and 'facts' not in response['items'][0] and 'source' in response['items'][0]
    with factory() as db:
        user = db.scalar(select(User).where(User.username=='place-reviewer')); user.is_admin=False
        role=Role(code='map_'+uuid4().hex[:8],name='仅地图',permissions_json=json.dumps(['geography.read','geography.write']))
        db.add(role);db.flush();user.role_id=role.id;db.commit()
    assert post(client,r,'/geography/points',{})['total'] == 0
    assert client.post('/api/geography/points',headers=r,json={'layer':'PLACE'}).status_code == 403
    assert client.get('/api/geography/PLACE/'+p['id'],headers=r).status_code == 403
    assert client.post('/api/geography/PLACE/'+p['id']+'/location',headers=headers(r),json={'version':0,'longitude':1,'latitude':1,'source':'x'}).status_code == 403
    assert client.post('/api/geography/points',headers=a,json={'layer':'PERSON'}).status_code == 422


def test_map_point_budget_reports_truncation_without_cross_org_counts(context):
    client, factory, a, _, b = prepare(context)
    with factory() as db:
        actor = db.scalar(select(User).where(User.username=='alice'))
        rows=[Place(org_id=actor.org_id,code='SYNTHETIC-'+str(i),name='合成场所 '+str(i),kind='OTHER',district='合成',address='合成',responsible='合成',management_basis='合成',created_by=actor.id) for i in range(501)]
        db.add_all(rows);db.flush()
        db.add_all([GeoLocation(org_id=actor.org_id,resource_type='PLACE',resource_id=row.id,longitude=110,latitude=30,source='合成坐标',updated_by=actor.id) for row in rows]);db.commit()
    result = post(client,a,'/geography/points',{})
    assert result['total']==501 and len(result['items'])==500 and result['truncated']
    assert post(client,b,'/geography/search',{})['total']==0


def test_offline_tiles_are_authenticated_bounded_and_confined(context,tmp_path,monkeypatch):
    client, _, a, _, _ = prepare(context)
    monkeypatch.setenv('WELLSPRING_MAP_TILE_DIR',str(tmp_path))
    folder=tmp_path/'0'/'0';folder.mkdir(parents=True)
    raw=b'\x89PNG\r\n\x1a\nSYNTHETIC'
    (folder/'0.png').write_bytes(raw)
    assert client.get('/api/geography/tiles/0/0/0.png').status_code == 401
    response=client.get('/api/geography/tiles/0/0/0.png',headers=a)
    assert response.status_code==200 and response.content==raw and response.headers['cache-control']=='private, no-store'
    assert client.get('/api/geography/tiles/21/0/0.png',headers=a).status_code==404
    assert client.get('/api/geography/tiles/0/1/0.png',headers=a).status_code==404
    assert client.get('/api/geography/config',headers=a).json()['tiles_available']
