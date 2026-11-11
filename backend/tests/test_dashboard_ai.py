import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from wellspring import ai_provider as provider
from wellspring.ai_models import AiRun, AiService
from wellspring.access_models import Role
from wellspring.models import Audit, Case, CaseInformation, User
from wellspring.security import password_hash
from test_workflow import context, auth, headers


@pytest.fixture
def model_server(monkeypatch,tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts'))
    from mock_model_service import start_mock_model
    server, calls = start_mock_model()
    monkeypatch.setenv('WELLSPRING_AI_ALLOWED_HOSTS', '127.0.0.1')
    monkeypatch.setenv('WELLSPRING_AI_API_KEY', 'synthetic-provider-secret')
    monkeypatch.delenv('WELLSPRING_AI_API_KEY_FILE', raising=False)
    monkeypatch.setenv('WELLSPRING_AI_SECRET_DIR',str(tmp_path/'model-keys'))
    yield f'http://127.0.0.1:{server.server_port}/v1', calls
    server.shutdown(); server.server_close()


def administrator(context):
    client, factory = context
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.is_admin = True; db.commit()
    return client, factory, auth(client, 'alice')


def configure(client, actor, address, model='synthetic-model'):
    current = client.get('/api/system/ai', headers=actor).json()
    response = client.post('/api/system/ai/update', headers=headers(actor), json={
        'version': current['version'], 'enabled': True, 'base_url': address, 'model': model,
        'timeout_seconds': 5, 'max_output_tokens': 128, 'token_parameter': 'max_tokens'})
    assert response.status_code == 200, response.text
    return response.json()


def test_dashboard_scope_module_permissions_hidden_intake_and_beijing_dates(context):
    client, factory = context
    a, b = auth(client, 'alice'), auth(client, 'bob')
    for actor, number in [(a, 'A'), (b, 'B')]:
        client.post('/api/cases', headers=headers(actor), json={'number': number, 'title': number})
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        db.add(CaseInformation(org_id=user.org_id, number='VISIBLE', created_by=user.id, alarm_type='测试类型'))
        db.add(CaseInformation(org_id=user.org_id, number='HIDDEN', created_by=user.id, deleted_at=datetime.now(timezone.utc)))
        db.commit()
    response = client.get('/api/dashboard/overview?days=7', headers=a)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['timezone'] == 'Asia/Shanghai' and len(result['trend']['dates']) == 7
    assert next(row for row in result['metrics'] if row['key'] == 'cases')['total'] == 1
    assert next(row for row in result['metrics'] if row['key'] == 'intake')['total'] == 1
    assert 'HIDDEN' not in response.text and 'VISIBLE' not in response.text
    with factory() as db:
        role = Role(code='scoped', name='大屏只读', permissions_json=json.dumps(['dashboard.read','cases.read']))
        db.add(role); db.flush(); user = db.scalar(select(User).where(User.username == 'alice')); user.role_id = role.id; db.commit()
    result = client.get('/api/dashboard/overview', headers=a).json()
    assert [row['key'] for row in result['metrics']] == ['cases']
    assert result['breakdowns'] == {}
    assert client.get('/api/ai/status', headers=a).status_code == 403
    assert client.get('/api/dashboard/overview?days=10', headers=b).status_code == 422
    assert client.get('/api/dashboard/overview').status_code == 401


def test_ai_configuration_secret_scope_check_and_errors(context, model_server):
    address, calls = model_server
    client, factory, root = administrator(context)
    bob = auth(client, 'bob')
    assert client.get('/api/system/ai', headers=bob).status_code == 403
    saved = configure(client, root, address)
    assert saved['api_key_configured'] and 'synthetic-provider-secret' not in json.dumps(saved)
    checked = client.post('/api/system/ai/check', headers=root, json={'version': saved['version']})
    assert checked.status_code == 200 and checked.json()['ok']
    assert calls[-1]['path'] == '/v1/chat/completions'
    assert calls[-1]['authorization'] == 'Bearer synthetic-provider-secret'
    assert calls[-1]['body']['stream'] is False
    rejected = client.post('/api/system/ai/update', headers=headers(root), json={**{key:saved[key] for key in ['version','enabled','model']}, 'base_url':'http://unapproved.invalid/v1'})
    assert rejected.status_code == 422 and rejected.json()['code'] == 'AI_HOST_NOT_ALLOWED'
    saved = configure(client, root, address, 'synthetic-auth-error')
    response = client.post('/api/system/ai/check', headers=root, json={'version': saved['version']})
    assert response.status_code == 200 and not response.json()['ok']
    assert 'private detail' not in response.text


def test_ai_generation_idempotency_personal_history_and_no_business_writes(context, model_server):
    address, calls = model_server
    client, factory, actor = administrator(context)
    configure(client, actor, address)
    body = {'mode':'summary','text':'合成原文 only-for-model','consent':True}
    assert client.post('/api/ai/runs', headers=headers(actor), json={**body,'consent':False}).status_code == 422
    request_headers = headers(actor)
    response = client.post('/api/ai/runs', headers=request_headers, json=body)
    assert response.status_code == 202, response.text
    identity = response.json()['id']
    assert client.post('/api/ai/runs', headers=request_headers, json=body).status_code == 202
    assert len(calls) == 1
    assert client.post('/api/ai/runs', headers=request_headers, json={**body,'text':'changed'}).status_code == 409
    result = client.get('/api/ai/runs/'+identity, headers=actor).json()
    assert result['status'] == 'SUCCEEDED' and result['draft']
    assert '<script>' in result['output_text']
    assert client.get('/api/ai/runs/'+identity, headers=auth(client,'bob')).status_code == 404
    with factory() as db:
        user = db.scalar(select(User).where(User.username=='alice'))
        db.add(User(username='colleague',org_id=user.org_id,password_hash=password_hash('test-password-123')));db.commit()
        assert db.scalar(select(func.count()).select_from(Case)) == 0
        run = db.get(AiRun,identity)
        assert run.input_sha256 == hashlib.sha256(body['text'].encode()).hexdigest()
        assert not hasattr(run,'input_text')
    assert client.get('/api/ai/runs/'+identity, headers=auth(client,'colleague')).status_code == 404


@pytest.mark.parametrize('model,expected',[('synthetic-auth-error','AI_AUTH_FAILED'),('synthetic-malformed','AI_INVALID_RESPONSE'),('synthetic-large','AI_RESPONSE_TOO_LARGE')])
def test_ai_upstream_failures_are_stored_without_raw_messages(context, model_server, model, expected):
    client, factory, actor = administrator(context)
    configure(client, actor, model_server[0], model)
    response = client.post('/api/ai/runs', headers=headers(actor), json={'mode':'extract','text':'合成原文','consent':True})
    assert response.status_code == 202, response.text
    result = client.get('/api/ai/runs/'+response.json()['id'],headers=actor).json()
    assert result['status']=='FAILED' and result['error_code']==expected
    assert 'private detail' not in json.dumps(result) and 'synthetic-provider-secret' not in json.dumps(result)


def test_ai_statistics_sends_only_scoped_aggregates_and_read_only_roles_cannot_generate(context, model_server):
    client,factory,actor=administrator(context);configure(client,actor,model_server[0])
    client.post('/api/cases',headers=headers(actor),json={'number':'PRIVATE-NUMBER','title':'PRIVATE-CASE-TITLE'})
    response=client.post('/api/ai/runs',headers=headers(actor),json={'mode':'dashboard','days':7,'consent':True})
    assert response.status_code==202,response.text
    payload=json.dumps(model_server[1][-1]['body'],ensure_ascii=False)
    assert 'PRIVATE-CASE-TITLE' not in payload and 'PRIVATE-NUMBER' not in payload
    user_message = json.loads(model_server[1][-1]['body']['messages'][1]['content'])
    summary = json.loads(user_message['资料'])
    assert summary['metrics'] and 'total' in summary['metrics'][0]
    assert client.post('/api/ai/runs',headers=headers(auth(client,'bob')),json={'text':'x','consent':True}).status_code==403


def test_ai_key_file_and_host_validation(tmp_path,monkeypatch):
    monkeypatch.delenv('WELLSPRING_AI_API_KEY',raising=False)
    path=tmp_path/'key';path.write_bytes(b'synthetic-key\r\n');monkeypatch.setenv('WELLSPRING_AI_API_KEY_FILE',str(path))
    assert provider.api_key()=='synthetic-key'
    path.write_bytes(b'\xef\xbb\xbfbad')
    with pytest.raises(provider.ProviderError):provider.api_key()
    for url in ['file:///tmp/input','http://name:password@localhost/v1','http://localhost/v1?key=x','http://localhost/v1/chat/completions']:
        with pytest.raises(provider.ProviderError):provider.base_url(url)


def test_ai_cancelled_or_revoked_generation_discards_late_output(context,model_server,monkeypatch):
    client,factory,actor=administrator(context);configure(client,actor,model_server[0])
    async def cancel_during_model(*_):
        with factory() as db:
            row=db.scalar(select(AiRun).where(AiRun.status=='RUNNING'))
            row.status='CANCELLED';db.commit()
        return {'text':'LATE-OUTPUT','truncated':False,'prompt_tokens':1,'completion_tokens':1}
    monkeypatch.setattr(provider,'complete',cancel_during_model)
    response=client.post('/api/ai/runs',headers=headers(actor),json={'text':'x','consent':True})
    result=client.get('/api/ai/runs/'+response.json()['id'],headers=actor).json()
    assert result['status']=='CANCELLED' and not result['output_text']
    async def revoke_during_model(*_):
        with factory() as db:
            user=db.scalar(select(User).where(User.username=='alice'));user.active=False;db.commit()
        return {'text':'LATE-OUTPUT','truncated':False,'prompt_tokens':1,'completion_tokens':1}
    monkeypatch.setattr(provider,'complete',revoke_during_model)
    response=client.post('/api/ai/runs',headers=headers(actor),json={'text':'x','consent':True})
    with factory() as db:
        row=db.get(AiRun,response.json()['id'])
        assert row.status=='FAILED' and row.error_code=='AI_ACCESS_REVOKED' and not row.output_text


def test_provider_total_timeout_and_do_not_follow_redirects(monkeypatch):
    import httpx
    original=httpx.AsyncClient
    async def handler(request):
        await asyncio.sleep(.1)
        return httpx.Response(200,json={})
    monkeypatch.setattr(provider.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    config=provider.Configuration('http://127.0.0.1/v1','synthetic',.02,128,'max_tokens','')
    with pytest.raises(provider.ProviderError,match='AI_TIMEOUT'):
        asyncio.run(provider.complete(config,[{'role':'user','content':'x'}]))
    seen=[]
    def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(302,headers={'Location':'http://unapproved.invalid/'})
    monkeypatch.setattr(provider.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(redirect),**kwargs))
    with pytest.raises(provider.ProviderError,match='AI_SERVICE_ERROR'):
        asyncio.run(provider.complete(config,[{'role':'user','content':'x'}]))
    assert seen==['http://127.0.0.1/v1/chat/completions']


def test_dashboard_midnight_uses_beijing_day(context):
    from wellspring.dashboard import overview
    _,factory=context
    instant=datetime(2026,11,11,17,0,tzinfo=timezone.utc)
    with factory() as db:
        user=db.scalar(select(User).where(User.username=='alice'))
        db.add(Case(org_id=user.org_id,number='BEIJING-DAY',title='合成',created_at=datetime(2026,11,11,16,30,tzinfo=timezone.utc)));db.commit()
        result=overview(db,user,7,instant)
        assert result['trend']['dates'][-1]=='2026-11-12'
        series=next(item for item in result['trend']['series'] if item['key']=='cases')
        assert series['values'][-1]==1 and sum(series['values'][:-1])==0


def test_key_input_model_discovery_unsaved_probe_and_persistence(context,model_server,monkeypatch):
    from wellspring import ai_secrets
    client,factory,actor=administrator(context)
    address,calls=model_server
    body={'version':0,'enabled':False,'base_url':address,'model':'','api_key_action':'replace','api_key':'synthetic-ui-key'}
    response=client.post('/api/system/ai/models',headers=actor,json=body)
    assert response.status_code==200,response.text
    assert response.json()['ids']==['synthetic-model','synthetic-other-model']
    assert calls[-1]['authorization']=='Bearer synthetic-ui-key' and calls[-1]['path']=='/v1/models'
    assert not ai_secrets.directory().exists()
    with factory() as db:assert db.get(AiService,'primary') is None
    body['model']='synthetic-model'
    response=client.post('/api/system/ai/test',headers=actor,json=body)
    assert response.status_code==200 and response.json()['ok']
    assert not ai_secrets.directory().exists()
    body['enabled']=True
    key=headers(actor)
    saved=client.post('/api/system/ai/update',headers=key,json=body)
    assert saved.status_code==200,saved.text
    assert saved.json()['api_key_configured'] and saved.json()['api_key_source']=='saved'
    assert 'synthetic-ui-key' not in saved.text
    assert client.post('/api/system/ai/update',headers=key,json=body).status_code==200
    assert len(list(ai_secrets.directory().glob('*.key')))==1
    with factory() as db:
        row=db.get(AiService,'primary');assert provider.api_key(row.api_key_ref)=='synthetic-ui-key'
        from wellspring.models import IdempotencyRecord
        assert all('synthetic-ui-key' not in (record.response_json or '') for record in db.scalars(select(IdempotencyRecord)))
    assert 'synthetic-ui-key' not in client.get('/api/system/ai',headers=actor).text
    body.update(version=saved.json()['version'],api_key_action='keep',api_key='')
    kept=client.post('/api/system/ai/update',headers=headers(actor),json=body)
    assert kept.status_code==200 and kept.json()['api_key_configured']
    client.post('/api/system/ai/test',headers=actor,json={**body,'version':kept.json()['version']})
    assert calls[-1]['authorization']=='Bearer synthetic-ui-key'
    cleared=client.post('/api/system/ai/update',headers=headers(actor),json={**body,'version':kept.json()['version'],'api_key_action':'clear'})
    assert cleared.status_code==200 and not cleared.json()['api_key_configured']
    client.post('/api/system/ai/test',headers=actor,json={**body,'version':cleared.json()['version']})
    assert calls[-1]['authorization']==''
    environment=client.post('/api/system/ai/update',headers=headers(actor),json={**body,'version':cleared.json()['version'],'api_key_action':'environment'})
    assert environment.json()['api_key_source']=='environment'
    client.post('/api/system/ai/test',headers=actor,json={**body,'version':environment.json()['version']})
    assert calls[-1]['authorization']=='Bearer synthetic-provider-secret'


def test_model_discovery_rejects_bad_key_and_non_admin_without_leaking_key(context,model_server):
    client,factory,actor=administrator(context)
    body={'version':0,'base_url':model_server[0],'api_key_action':'replace','api_key':'synthetic-bad-key'}
    response=client.post('/api/system/ai/models',headers=actor,json=body)
    assert response.status_code==502 and response.json()['code']=='AI_AUTH_FAILED'
    assert 'private upstream detail' not in response.text and 'synthetic-bad-key' not in response.text
    assert client.post('/api/system/ai/models',headers=auth(client,'bob'),json=body).status_code==403
    body['api_key']='invalid\nkey'
    assert client.post('/api/system/ai/test',headers=actor,json=body).status_code==422
