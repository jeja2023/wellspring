from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from wellspring.db import Base, get_db
from wellspring.main import app
from wellspring.models import Organization, User, WeightEvent
from wellspring.security import password_hash

@pytest.fixture
def context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
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
    assert client.post("/api/evidence",headers=headers(b),json={"case_id":case.json()["id"],"label":"示例","weight":"1","reason":"登记"}).status_code == 404
    assert client.post("/api/cases",headers=headers(a),json={"number":"A-01","title":"重复"}).status_code == 409
    assert client.post("/api/logout",headers=a).status_code == 200
    assert client.get("/api/cases",headers=a).status_code == 401

def test_weight_transfer_is_conserved(context):
    client, factory = context
    a=auth(client,"alice")
    case=client.post("/api/cases",headers=headers(a),json={"number":"A-01","title":"示例"}).json()
    original=client.post("/api/evidence",headers=headers(a),json={"case_id":case["id"],"label":"原物","weight":"100.000000","reason":"初称"})
    assert original.status_code == 201
    item=original.json()
    response=client.post(f"/api/evidence/{item['id']}/samples",headers=headers(a),json={"label":"检材","weight":"10.000000","reason":"分样","source_version":1})
    assert response.status_code == 201
    objects=client.get("/api/evidence",headers=a).json()["items"]
    assert sum(Decimal(x["balance"]) for x in objects) == Decimal("100.000000")
    assert sorted(Decimal(x["balance"]) for x in objects) == [Decimal("10"),Decimal("90")]
    assert client.post(f"/api/evidence/{item['id']}/samples",headers=headers(a),json={"label":"超量","weight":"91","reason":"分样","source_version":2}).status_code == 409
    assert client.post(f"/api/evidence/{item['id']}/samples",headers=headers(a),json={"label":"过精","weight":"0.0000001","reason":"分样","source_version":2}).status_code == 422
    with factory() as db:
        rows=db.scalars(select(WeightEvent)).all()
        assert len(rows)==3
        assert sum((x.delta for x in rows),Decimal(0))==Decimal("100")
        transfer=[x for x in rows if x.kind.startswith("SAMPLE")]
        assert len({x.operation_id for x in transfer}) == 1


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
    item = client.post("/api/evidence",headers=headers(a),json={"case_id":first.json()["id"],"label":"原物","weight":"100","reason":"初称"}).json()
    sample_headers = headers(a)
    body = {"label":"检材","weight":"10","reason":"分样","source_version":1}
    first_sample = client.post(f"/api/evidence/{item['id']}/samples",headers=sample_headers,json=body)
    replay_sample = client.post(f"/api/evidence/{item['id']}/samples",headers=sample_headers,json=body)
    assert first_sample.status_code == replay_sample.status_code == 201
    assert first_sample.json() == replay_sample.json()
    stale = client.post(f"/api/evidence/{item['id']}/samples",headers=headers(a),json={**body,"label":"其他检材"})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    objects = client.get("/api/evidence",headers=a).json()["items"]
    assert len(objects) == 2 and sum(Decimal(x["balance"]) for x in objects) == Decimal("100")
    with factory() as db:
        assert len(db.scalars(select(WeightEvent)).all()) == 3


def test_evidence_replay_and_revoked_access(context):
    client, factory = context
    a, b = auth(client, "alice"), auth(client, "bob")
    case = client.post("/api/cases",headers=headers(a),json={"number":"A-2","title":"示例"}).json()
    saved_headers = headers(a)
    body = {"case_id":case["id"],"label":"原物","weight":"5","reason":"初称"}
    first = client.post("/api/evidence",headers=saved_headers,json=body)
    replay = client.post("/api/evidence",headers=saved_headers,json=body)
    assert first.status_code == replay.status_code == 201 and first.json() == replay.json()
    assert client.get("/api/evidence",headers=b).json()["total"] == 0
    assert client.get(f"/api/evidence/{first.json()['id']}/events",headers=b).status_code == 404
    event_page = client.get(f"/api/evidence/{first.json()['id']}/events?page_size=1",headers=a).json()
    assert event_page["total"] == 1 and event_page["request_id"]
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        user.active = False
        db.commit()
    assert client.post("/api/evidence",headers=saved_headers,json=body).status_code == 401
