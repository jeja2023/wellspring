import json
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import func,select,text
from wellspring.main import app
from wellspring.models import User,Audit
from wellspring.analysis_models import AnalysisAsset,AnalysisAssetEvent
from wellspring.access_models import Role
from test_workflow import context,auth,headers


def body(category='DATASET',configuration=None,**values):
    return {'code':'asset_'+uuid4().hex[:12],'name':'合成分析资料','category':category,'description':'合成验证用途','configuration':configuration or {'fields':[{'name':'record_count','type':'number'}]},**values}


def create(client,actor,area,data):
    response=client.post('/api/analysis/'+area,headers=headers(actor),json=data)
    assert response.status_code==201,response.text
    return response.json()


def transition(client,actor,area,row,action):
    response=client.post(f"/api/analysis/{area}/{row['id']}/transition",headers=headers(actor),json={'version':row['version'],'action':action,'note':'合成操作说明'})
    assert response.status_code==200,response.text
    return response.json()


def test_project_model_tactic_lifecycle_and_sample_validation(context):
    client,factory=context;actor=auth(client,'alice')
    project=create(client,actor,'modeling',body());project=transition(client,actor,'modeling',project,'ACTIVATE')
    model=create(client,actor,'models',body('SCORE',{'rules':[{'field':'record_count','operator':'gte','value':3,'points':40}]},project_id=project['id']))
    response=client.post(f"/api/analysis/models/{model['id']}/validate",headers=actor,json={'version':1,'records':[{'record_count':5},{'record_count':1},{}]})
    assert response.status_code==200,response.text
    assert [row['score'] for row in response.json()['rows']]==[40,0,None]
    model=transition(client,actor,'models',model,'ACTIVATE')
    tactic=create(client,actor,'tactics',body('CLUE',{'steps':'核对来源\n验证规则\n人工复核','applicability':'合成场景'},project_id=project['id'],model_id=model['id']))
    tactic=transition(client,actor,'tactics',tactic,'ACTIVATE')
    response=client.post(f"/api/analysis/models/{model['id']}/transition",headers=headers(actor),json={'version':model['version'],'action':'DEACTIVATE','note':'合成'})
    assert response.status_code==409 and response.json()['code']=='ASSET_IN_USE'
    tactic=transition(client,actor,'tactics',tactic,'DEACTIVATE');tactic=transition(client,actor,'tactics',tactic,'ARCHIVE')
    model=transition(client,actor,'models',model,'DEACTIVATE');project=transition(client,actor,'modeling',project,'DEACTIVATE')
    assert tactic['status']=='ARCHIVED' and project['status']=='DRAFT'
    detail=client.get(f"/api/analysis/models/{model['id']}",headers=actor).json()
    assert detail['history']['total']==3
    assert detail['history']['items'][-1]['snapshot']['configuration']['rules'][0]['points']==40


def test_authorization_scope_references_idempotency_and_versions(context):
    client,factory=context;a,b=auth(client,'alice'),auth(client,'bob');data=body();key=headers(a)
    response=client.post('/api/analysis/modeling',headers=key,json=data);assert response.status_code==201
    row=response.json();assert client.post('/api/analysis/modeling',headers=key,json=data).json()['id']==row['id']
    assert client.get('/api/analysis/modeling/'+row['id'],headers=b).status_code==404
    assert client.post('/api/analysis/modeling/search',headers=b,json={}).json()['total']==0
    assert client.post('/api/analysis/models',headers=headers(b),json=body('COLLISION',{'conditions':[{'field':'n','operator':'eq','value':1}]},project_id=row['id'])).status_code==404
    with factory() as db:
        user=db.scalar(select(User).where(User.username=='alice'));role=Role(code='read_'+uuid4().hex[:8],name='只读建模',permissions_json=json.dumps(['modeling.read']));db.add(role);db.flush();user.role_id=role.id;db.commit()
    assert client.post('/api/analysis/modeling/search',headers=a,json={}).status_code==200
    assert client.post('/api/analysis/modeling',headers=headers(a),json=body()).status_code==403
    assert client.get('/api/analysis/models/any',headers=a).status_code==403
    assert client.get('/api/analysis/unknown/any',headers=a).status_code==403


def test_invalid_configuration_duplicate_and_optimistic_edit(context):
    client,_=context;a=auth(client,'alice');data=body();row=create(client,a,'modeling',data)
    assert client.post('/api/analysis/modeling',headers=headers(a),json=data).status_code==409
    assert client.post('/api/analysis/models',headers=headers(a),json=body('COLLISION',{'conditions':[{'field':'x','operator':'__import__','value':'os'}]})).status_code==422
    assert client.post('/api/analysis/models',headers=headers(a),json=body('SCORE',{'rules':[{'field':'x','operator':'eq','value':1,'points':101}]})).status_code==422
    edit={name:value for name,value in data.items() if name!='code'};edit['version']=1;edit['name']='合成修订'
    response=client.post(f"/api/analysis/modeling/{row['id']}/update",headers=headers(a),json=edit)
    assert response.status_code==200 and response.json()['version']==2
    assert client.post(f"/api/analysis/modeling/{row['id']}/update",headers=headers(a),json=edit).status_code==409


def test_asset_audit_failure_rolls_back_fact_and_history(context):
    client,factory=context;actor=auth(client,'alice');engine=factory.kw['bind']
    with engine.begin() as connection:connection.execute(text("CREATE TRIGGER reject_asset_audit BEFORE INSERT ON audit_events WHEN NEW.action='ANALYSIS_ASSET_CREATE' BEGIN SELECT RAISE(ABORT,'synthetic audit error'); END"))
    with TestClient(app,raise_server_exceptions=False) as safe:
        assert safe.post('/api/analysis/modeling',headers=headers(actor),json=body()).status_code==500
    with engine.begin() as connection:connection.execute(text('DROP TRIGGER reject_asset_audit'))
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AnalysisAsset))==0
        assert db.scalar(select(func.count()).select_from(AnalysisAssetEvent))==0
