from uuid import uuid4
from sqlalchemy import select, text
from fastapi.testclient import TestClient
from wellspring.main import app
from wellspring.models import Audit, Clue, IdempotencyRecord, IntelligenceEvent, User
from wellspring.security import password_hash
from test_workflow import context, auth, headers


def create_reviewer(factory):
    with factory() as db:
        alice = db.scalar(select(User).where(User.username == "alice"))
        user = User(username="reviewer", org_id=alice.org_id, password_hash=password_hash("test-password-123"))
        db.add(user); db.commit()
        return alice.id, user.id


def test_clue_task_flow_and_review_separation(context):
    client, factory = context
    alice_id, reviewer_id = create_reviewer(factory)
    alice, reviewer, other = auth(client,"alice"), auth(client,"reviewer"), auth(client,"bob")
    body={"title":"虚构线索","summary":"待核查的示例","source":"虚构来源"}
    same=headers(alice)
    created=client.post("/api/intelligence/clues",headers=same,json=body)
    assert created.status_code == 201
    clue=created.json(); cid=clue["id"]
    assert client.post("/api/intelligence/clues",headers=same,json=body).json()["id"] == cid
    assert client.post("/api/intelligence/clues",headers=same,json={**body,"title":"不同"}).json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert client.get("/api/intelligence/clues",headers=other).json()["total"] == 0
    assert client.get(f"/api/intelligence/clues/{cid}/detail",headers=other).status_code == 404
    taskbody={"clue_version":1,"objective":"核查示例","assignee_id":alice_id}
    assert client.post(f"/api/intelligence/clues/{cid}/tasks",headers=headers(alice),json=taskbody).status_code == 409
    review_headers=headers(alice)
    review=client.post(f"/api/intelligence/clues/{cid}/review",headers=review_headers,json={"version":1,"note":"人工核验示例"})
    assert review.status_code == 200 and review.json()["version"] == 2
    assert client.post(f"/api/intelligence/clues/{cid}/review",headers=review_headers,json={"version":1,"note":"人工核验示例"}).status_code == 200
    assert client.post(f"/api/intelligence/clues/{cid}/tasks",headers=headers(alice),json={**taskbody,"clue_version":2,"assignee_id":"unknown"}).status_code == 404
    taskheaders=headers(alice)
    taskbody["clue_version"]=2
    task=client.post(f"/api/intelligence/clues/{cid}/tasks",headers=taskheaders,json=taskbody)
    assert task.status_code == 201
    tid=task.json()["id"]
    assert client.post(f"/api/intelligence/clues/{cid}/tasks",headers=taskheaders,json=taskbody).json()["id"] == tid
    submit={"version":1,"action":"SUBMIT","note":"示例核查","result":"NO_FINDING"}
    sh=headers(alice)
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=sh,json=submit).json()["status"] == "PENDING_REVIEW"
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=sh,json=submit).status_code == 200
    close={"version":2,"action":"CLOSE","note":"示例复核"}
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=headers(alice),json=close).status_code == 403
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=headers(other),json=close).status_code == 404
    returned=client.post(f"/api/intelligence/tasks/{tid}/transition",headers=headers(reviewer),json={"version":2,"action":"RETURN","note":"补充材料"})
    assert returned.json()["status"] == "RETURNED"
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=headers(alice),json=submit).status_code == 409
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=headers(alice),json={**submit,"version":3,"result":"VERIFIED"}).status_code == 200
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=headers(reviewer),json={**close,"version":4}).json()["status"] == "CLOSED"
    detail=client.get(f"/api/intelligence/clues/{cid}/detail",headers=alice).json()
    assert detail["task"]["status"] == "CLOSED"
    assert [e["result"] for e in detail["events"]["items"] if e["action"]=="SUBMIT"] == ["NO_FINDING","VERIFIED"]
    with factory() as db:
        assert len(db.scalars(select(IntelligenceEvent).where(IntelligenceEvent.clue_id==cid)).all()) == 7
        assert db.scalar(select(Audit).where(Audit.action=="INVESTIGATION_CLOSE")) is not None


def test_invalid_and_unauthenticated_clue_requests(context):
    client, factory = context
    assert client.get("/api/intelligence/clues").status_code == 401
    alice=auth(client,"alice")
    assert client.post("/api/intelligence/clues",headers=headers(alice),json={"title":"   ","summary":"x","source":"x"}).status_code == 422
    assert client.get("/api/intelligence/clues?page_size=101",headers=alice).status_code == 422


def test_audit_failure_rolls_back_clue_and_idempotency(context):
    client, factory = context
    alice = auth(client, "alice")
    engine = factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(text("CREATE TRIGGER fail_clue_audit BEFORE INSERT ON audit_events WHEN NEW.action = 'CLUE_CREATE' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"))
    request_headers = headers(alice)
    body = {"title":"虚构线索","summary":"测试摘要","source":"测试来源"}
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        response = safe_client.post("/api/intelligence/clues", headers=request_headers, json=body)
        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"
    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER fail_clue_audit"))
    with factory() as db:
        assert db.scalars(select(Clue)).all() == []
        assert db.scalars(select(IdempotencyRecord).where(IdempotencyRecord.operation == "CLUE_CREATE")).all() == []
    assert client.post("/api/intelligence/clues",headers=request_headers,json=body).status_code == 201


def test_due_date_and_personal_task_scope(context):
    client, factory = context
    alice_id, reviewer_id = create_reviewer(factory)
    alice, reviewer, other = auth(client,"alice"), auth(client,"reviewer"), auth(client,"bob")
    clue = client.post("/api/intelligence/clues",headers=headers(alice),json={"title":"虚构期限线索","summary":"示例","source":"虚构"}).json()
    cid=clue["id"]
    assert client.post(f"/api/intelligence/clues/{cid}/review",headers=headers(alice),json={"version":1,"note":"核验"}).status_code == 200
    task_body={"clue_version":2,"objective":"核查","assignee_id":alice_id,"due_date":"2020-01-02"}
    assert client.post(f"/api/intelligence/clues/{cid}/tasks",headers=headers(alice),json={**task_body,"due_date":"2020-02-30"}).status_code == 422
    task=client.post(f"/api/intelligence/clues/{cid}/tasks",headers=headers(alice),json=task_body)
    assert task.status_code == 201 and task.json()["due_date"] == "2020-01-02"
    mine=client.get("/api/intelligence/tasks/mine",headers=alice).json()
    assert mine["total"] == 1 and mine["items"][0]["clue_title"] == "虚构期限线索"
    assert mine["items"][0]["status"] == "OPEN"  # 过期日期不自动改变状态。
    assert client.get("/api/intelligence/tasks/mine",headers=reviewer).json()["total"] == 0
    assert client.get("/api/intelligence/tasks/mine",headers=other).json()["total"] == 0
    assert client.get("/api/intelligence/tasks/mine").status_code == 401
    assert client.get(f"/api/intelligence/clues/{cid}/detail",headers=alice).json()["task"]["due_date"] == "2020-01-02"
    tid=task.json()["id"]
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=headers(alice),json={"version":1,"action":"SUBMIT","note":"测试","result":"NO_FINDING"}).status_code == 200
    assert client.post(f"/api/intelligence/tasks/{tid}/transition",headers=headers(reviewer),json={"version":2,"action":"CLOSE","note":"复核"}).status_code == 200
    assert client.get("/api/intelligence/tasks/mine",headers=alice).json()["total"] == 0
