from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from wellspring.db import Base, get_db
from wellspring.main import app
from wellspring.models import Organization, User
from wellspring.security import password_hash

@pytest.fixture
def context():
    from wellspring.http_limits import login_limiter
    login_limiter.clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        import json
        from wellspring.access_models import Role
        from wellspring.access_policy import DEFAULT_ROLE_ID,LEGACY_PERMISSIONS
        db.add(Role(id=DEFAULT_ROLE_ID,code='business_user',name='业务用户',permissions_json=json.dumps(sorted(LEGACY_PERMISSIONS))))
        a, b = Organization(name="A"), Organization(name="B")
        db.add_all([a,b]); db.flush()
        db.add_all([User(username="alice",password_hash=password_hash("test-password-123"),org_id=a.id),User(username="bob",password_hash=password_hash("test-password-123"),org_id=b.id)])
        db.commit()
    def override():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()

def auth(client, user):
    response=client.post("/api/login",json={"username":user,"password":"test-password-123"})
    assert response.status_code == 200
    return {"Authorization":"Bearer "+response.json()["token"]}

def headers(auth_headers):
    return {**auth_headers, "Idempotency-Key": str(uuid4())}

def test_scope_and_sessions(context):
    client, factory = context
    assert client.get("/api/cases").status_code == 401
    a, b = auth(client,"alice"), auth(client,"bob")
    case = client.post("/api/cases",headers=headers(a),json={"number":"A-01","title":"示例案件"})
    assert case.status_code == 201
    assert client.get("/api/cases",headers=b).json()["items"] == []
    assert client.post("/api/cases",headers=headers(a),json={"number":"A-01","title":"重复"}).status_code == 409
    assert client.post("/api/logout",headers=a).status_code == 200
    assert client.get("/api/cases",headers=a).status_code == 401



def test_pagination_and_validation(context):
    client, _ = context
    a, b = auth(client, "alice"), auth(client, "bob")
    for n in range(5):
        assert client.post("/api/cases",headers=headers(a),json={"number":f"A-{n}","title":"示例"}).status_code == 201
    first = client.get("/api/cases?page=1&page_size=2&sort=number&order=asc",headers=a).json()
    second = client.get("/api/cases?page=2&page_size=2&sort=number&order=asc",headers=a).json()
    assert first["total"] == 5 and first["has_more"] is True
    assert [x["number"] for x in first["items"]] == ["A-0", "A-1"]
    assert [x["number"] for x in second["items"]] == ["A-2", "A-3"]
    assert client.get("/api/cases",headers=b).json()["total"] == 0
    assert client.get("/api/cases?page_size=101",headers=a).status_code == 422
    assert client.get("/api/cases?sort=bad",headers=a).json()["code"] == "VALIDATION_ERROR"
    error = client.get("/api/cases?page=0",headers=a).json()
    assert error["code"] == "VALIDATION_ERROR" and error["request_id"]

def test_idempotency_and_stale_version(context):
    client, factory = context
    a = auth(client, "alice")
    case_headers = headers(a)
    case_body = {"number":"A-1","title":"示例"}
    first = client.post("/api/cases",headers=case_headers,json=case_body)
    replay = client.post("/api/cases",headers=case_headers,json=case_body)
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json() and replay.headers["X-Idempotent-Replay"] == "true"
    assert client.post("/api/cases",headers=case_headers,json={**case_body,"title":"不同"}).json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert client.post("/api/cases",headers=a,json=case_body).status_code == 400
