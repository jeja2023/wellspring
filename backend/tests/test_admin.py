from sqlalchemy import select
from wellspring.models import Audit, Organization, User
from test_workflow import context, auth


def test_admin_permission_is_enforced_server_side(context):
    client, factory = context
    alice, bob = auth(client, 'alice'), auth(client, 'bob')
    assert client.get('/api/admin/status').status_code == 401
    assert client.get('/api/admin/status', headers=alice).status_code == 403
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.is_admin = True
        db.commit()
    assert client.get('/api/admin/status', headers=alice).json() == {'username': 'alice', 'is_admin': True}
    assert client.get('/api/admin/status', headers=bob).status_code == 403
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.is_admin = False
        db.commit()
    assert client.get('/api/admin/status', headers=alice).status_code == 403


def test_session_refresh_uses_current_account_state(context):
    client, factory = context
    alice = auth(client, 'alice')
    assert client.get('/api/session').status_code == 401
    assert client.get('/api/session', headers=alice).json()['is_admin'] is False
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.is_admin = True
        db.commit()
    assert client.get('/api/session', headers=alice).json()['is_admin'] is True
    assert client.post('/api/logout', headers=alice).status_code == 200
    assert client.get('/api/session', headers=alice).status_code == 401


def test_bootstrap_initial_admin_is_explicit_and_cannot_repeat(context, monkeypatch):
    from wellspring import bootstrap
    client, factory = context
    monkeypatch.setattr(bootstrap, 'SessionLocal', factory)
    answers = iter(['newadmin'])
    monkeypatch.setattr('builtins.input', lambda _prompt: next(answers))
    monkeypatch.setattr(bootstrap.getpass, 'getpass', lambda _prompt: 'test-password-123')
    bootstrap.main(initial_admin=True)
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'newadmin'))
        assert user.is_admin
        assert db.get(Organization, user.org_id).name == '系统运维'
        assert db.scalar(select(Audit).where(Audit.action == 'INITIAL_ADMIN_ASSIGN', Audit.object_id == user.id))
    answers = iter(['another'])
    try:
        bootstrap.main(initial_admin=True)
        assert False, 'must reject a second initial administrator'
    except SystemExit as exc:
        assert '已存在管理员' in str(exc)
    with factory() as db:
        assert db.scalar(select(User).where(User.username == 'another')) is None


def test_system_audit_requires_admin_and_search_is_paginated(context):
    client, factory = context
    alice, bob = auth(client, 'alice'), auth(client, 'bob')
    path = '/api/admin/audit/search'
    assert client.post(path, json={}).status_code == 401
    assert client.post(path, headers=bob, json={}).status_code == 403
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.is_admin = True
        db.commit()
    first = client.post(path, headers=alice, json={'username': 'bob', 'action': 'LOGIN', 'page_size': 1})
    assert first.status_code == 200
    assert first.json()['total'] == 1
    item = first.json()['items'][0]
    assert item['username'] == 'bob' and item['organization'] == 'B' and item['action'] == 'LOGIN'
    assert 'password' not in item and 'token' not in item
    assert client.post(path, headers=alice, json={'username': '%'}).json()['total'] == 0
    assert client.post(path, headers=alice, json={'page_size': 101}).status_code == 422
    with factory() as db:
        assert db.scalar(select(Audit).where(Audit.action == 'SYSTEM_AUDIT_SEARCH'))


def test_personal_audit_preserves_history_after_organization_change(context):
    client, factory = context
    alice, bob = auth(client, 'alice'), auth(client, 'bob')
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        other = db.scalar(select(Organization).where(Organization.name == 'B'))
        user.org_id = other.id
        db.commit()
    records = client.get('/api/audit/mine', headers=alice).json()['items']
    assert any(record['action'] == 'LOGIN' for record in records)
    bob_records = client.get('/api/audit/mine', headers=bob).json()['items']
    assert not {record['id'] for record in records} & {record['id'] for record in bob_records}
