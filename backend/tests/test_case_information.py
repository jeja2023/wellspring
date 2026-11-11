from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wellspring.models import CaseInformation, Audit
from wellspring.main import app
from test_workflow import context, auth, headers


def test_case_information_import_search_update_soft_delete(context):
    client, factory = context
    alice, bob = auth(client, 'alice'), auth(client, 'bob')
    route = '/api/case-information'
    body = {'rows': [{'接警编号': '  0001  ', '报警人': '虚构姓名', '接警类型': '测试类型'}, {'接警编号': '0002', '结果': '待核查'}]}
    assert client.post(route + '/import', json=body).status_code == 401
    same = headers(alice)
    assert client.post(route + '/import', headers=same, json=body).json()['created'] == 2
    assert client.post(route + '/import', headers=same, json=body).json()['created'] == 2
    assert client.post(route + '/import', headers=headers(bob), json={'rows': [{'接警编号': '0001'}]}).status_code == 409
    assert client.post(route + '/import', headers=headers(alice), json={'rows': [{'接警编号': 'X'}, {'接警编号': 'X'}]}).status_code == 409
    assert client.post(route + '/search', headers=bob, json={}).json()['total'] == 0
    found = client.post(route + '/search', headers=alice, json={'keyword': '虚构姓名', 'page_size': 1}).json()
    assert found['total'] == 1 and found['statistics']['types'][0]['count'] == 1
    assert len(client.post(route + '/export', headers=alice, json={'keyword': '虚构姓名'}).json()['items']) == 1
    assert client.post(route + '/export', headers=bob, json={}).json()['items'] == []
    item = found['items'][0]
    assert item['接警编号'] == '0001' and item['备注'] is None
    url = route + '/' + item['id']
    assert client.post(url + '/update', headers=headers(bob), json={'version': 1, 'fields': {'接警编号': '0001'}}).status_code == 404
    assert client.post(url + '/update', headers=headers(alice), json={'version': 1, 'fields': {'接警编号': '0001', '备注': '虚构备注'}}).json()['version'] == 2
    assert client.post(url + '/delete', headers=headers(alice), json={'version': 1}).status_code == 409
    delete_headers = headers(alice)
    assert client.post(url + '/delete', headers=delete_headers, json={'version': 2}).status_code == 200
    assert client.post(url + '/delete', headers=delete_headers, json={'version': 2}).status_code == 200
    assert client.post(route + '/search', headers=alice, json={}).json()['total'] == 1
    assert client.post(route + '/import', headers=headers(alice), json={'rows': [{'接警编号': '0001'}]}).status_code == 409
    with factory() as db:
        stored = db.scalar(select(CaseInformation).where(CaseInformation.number == '0001'))
        assert stored.deleted_at is not None and stored.note == '虚构备注'
        assert db.scalar(select(Audit).where(Audit.action == 'CASE_INFORMATION_DELETE', Audit.object_id == item['id']))


def test_import_audit_failure_rolls_back_entire_batch(context):
    client, factory = context
    alice = auth(client, 'alice')
    engine = factory.kw['bind']
    with engine.begin() as db:
        db.execute(text("CREATE TRIGGER fail_case_information_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'CASE_INFORMATION_IMPORT' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    with TestClient(app, raise_server_exceptions=False) as safe:
        response = safe.post('/api/case-information/import', headers=headers(alice), json={'rows': [{'接警编号': 'ONE'}, {'接警编号': 'TWO'}]})
        assert response.status_code == 500
    with engine.begin() as db:
        db.execute(text('DROP TRIGGER fail_case_information_audit'))
    with factory() as db:
        assert db.scalars(select(CaseInformation)).all() == []


def test_admin_can_view_cross_organization_and_restore_deleted(context):
    from wellspring.models import User
    client, factory = context
    alice, bob = auth(client, 'alice'), auth(client, 'bob')
    root = '/api/case-information'
    assert client.post(root + '/import', headers=headers(bob), json={'rows': [{'接警编号': 'B-1', '结果': '待核查'}]}).status_code == 201
    item = client.post(root + '/search', headers=bob, json={}).json()['items'][0]
    assert client.post(root + '/admin/deleted', headers=bob, json={}).status_code == 403
    assert client.post(root + '/search', headers=alice, json={}).json()['total'] == 0
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.is_admin = True
        db.commit()
    response = client.post(root + '/search', headers=alice, json={}).json()
    assert response['total'] == 1 and response['options']['results'] == ['待核查']
    assert client.post(root + '/export', headers=alice, json={}).json()['items'][0]['id'] == item['id']
    assert client.post(root + f"/{item['id']}/delete", headers=headers(alice), json={'version': 1}).status_code == 200
    hidden = client.post(root + '/admin/deleted', headers=alice, json={}).json()
    assert hidden['total'] == 1 and hidden['items'][0]['organization'] == 'B'
    url = root + f"/admin/{item['id']}/restore"
    assert client.post(url, headers=headers(bob), json={'version': 2}).status_code == 403
    assert client.post(url, headers=headers(alice), json={'version': 1}).status_code == 409
    key = headers(alice)
    assert client.post(url, headers=key, json={'version': 2}).json()['restored'] is True
    assert client.post(url, headers=key, json={'version': 2}).json()['restored'] is True
    assert client.post(root + '/search', headers=bob, json={}).json()['total'] == 1
    with factory() as db:
        assert db.scalar(select(Audit).where(Audit.action == 'CASE_INFORMATION_RESTORE', Audit.object_id == item['id']))
