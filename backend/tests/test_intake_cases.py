import json
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from wellspring.models import Audit, Case, CaseInformation, User
from wellspring.intake_models import IntakeCaseLink
from wellspring.main import app
from test_workflow import context, auth, headers


def intake(client, actor, number="ALARM-1"):
    assert client.post("/api/case-information/import", headers=headers(actor), json={"rows": [{"接警编号": number, "报警内容": "合成原始内容", "备注": "合成保留备注"}]}).status_code == 201
    return client.post("/api/case-information/search", headers=actor, json={"keyword": number, "include_case_links": True}).json()["items"][0]


def new_body(source, number="CASE-1"):
    return {"source_version": source["version"], "mode": "NEW", "number": number, "title": "合成案件记录", "basis": "合成转办依据"}


def transfer(client, actor, source, body=None, key=None):
    return client.post(f"/api/case-information/{source['id']}/case-link", headers=key or headers(actor), json=body or new_body(source))


def test_explicit_create_keeps_source_and_snapshot_without_duplicate_case(context):
    client, factory = context; actor = auth(client, "alice")
    source = intake(client, actor); key = headers(actor)
    response = transfer(client, actor, source, key=key)
    assert response.status_code == 201, response.text
    assert transfer(client, actor, source, key=key).json() == response.json()
    assert transfer(client, actor, source).status_code == 409
    case = response.json()
    detail = client.get(f"/api/case-information/{source['id']}/detail", headers=actor).json()
    assert detail["version"] == 2 and detail["备注"] == "合成保留备注" and detail["case_link"]["id"] == case["id"]
    route = f"/api/cases/{case['id']}/intake-sources"
    sources = client.get(route, headers=actor).json()
    assert sources["total"] == 1 and sources["items"][0]["source_version"] == 1
    link = sources["items"][0]
    assert client.post(f"/api/case-information/{source['id']}/update", headers=headers(actor), json={"version": 2, "fields": {"接警编号": "CHANGED", "报警内容": "后续更正"}}).status_code == 200
    assert client.post(f"/api/case-information/{source['id']}/delete", headers=headers(actor), json={"version": 3}).status_code == 200
    snapshot = client.get(route + "/" + link["id"], headers=actor).json()
    assert snapshot["fields"]["接警编号"] == "ALARM-1" and snapshot["fields"]["报警内容"] == "合成原始内容"
    assert client.get(route, headers=actor).json()["items"][0]["source_hidden"] is True
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Case)) == 1
        assert db.scalar(select(func.count()).select_from(IntakeCaseLink)) == 1
        assert db.scalar(select(Audit).where(Audit.action == "INTAKE_CASE_LINK"))


def test_associate_existing_and_revoke_preserve_both_records(context):
    client, factory = context; actor = auth(client, "alice")
    source = intake(client, actor)
    target = client.post("/api/cases", headers=headers(actor), json={"number": "EXISTING", "title": "原有案件"}).json()
    body = {"source_version": 1, "mode": "EXISTING", "case_id": target["id"], "basis": "核对后关联"}
    response = transfer(client, actor, source, body).json()
    assert response["created_case"] is False
    route = f"/api/cases/{target['id']}/intake-sources"
    link = client.get(route, headers=actor).json()["items"][0]
    key = headers(actor); revoke = {"version": 1, "reason": "合成更正"}
    assert client.post(route + f"/{link['id']}/revoke", headers=key, json=revoke).status_code == 200
    assert client.post(route + f"/{link['id']}/revoke", headers=key, json=revoke).status_code == 200
    assert client.post(route + f"/{link['id']}/revoke", headers=headers(actor), json=revoke).status_code == 409
    fresh = client.get(f"/api/case-information/{source['id']}/detail", headers=actor).json()
    assert fresh["version"] == 3 and fresh["case_link"] is None
    response = transfer(client, actor, fresh, {**body, "source_version": 3})
    assert response.status_code == 201
    assert {row["status"] for row in client.get(route, headers=actor).json()["items"]} == {"ACTIVE", "REVOKED"}
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Case)) == 1
        assert db.get(CaseInformation, source["id"]).deleted_at is None


def test_cross_org_admin_view_does_not_grant_conversion_or_case_access(context):
    client, factory = context; a, b = auth(client, "alice"), auth(client, "bob")
    source = intake(client, b)
    assert transfer(client, a, source).status_code == 404
    other = client.post("/api/cases", headers=headers(a), json={"number": "A", "title": "A"}).json()
    assert transfer(client, b, source, {"source_version": 1, "mode": "EXISTING", "case_id": other["id"], "basis": "x"}).status_code == 404
    case = transfer(client, b, source).json()
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "alice")); user.is_admin = True; db.commit()
    detail = client.get(f"/api/case-information/{source['id']}/detail", headers=a).json()
    assert detail["can_link_case"] is False and detail["case_link"] == {"linked": True, "accessible": False}
    assert transfer(client, a, source).status_code == 404
    assert client.get(f"/api/cases/{case['id']}/intake-sources", headers=a).status_code == 404


def test_hidden_stale_duplicate_and_ambiguous_inputs_do_not_create_cases(context):
    client, factory = context; a = auth(client, "alice"); source = intake(client, a)
    assert transfer(client, a, source, {**new_body(source), "case_id": "also-target"}).status_code == 422
    assert transfer(client, a, source, {**new_body(source), "source_version": 9}).status_code == 409
    target = client.post("/api/cases", headers=headers(a), json={"number": "CASE-1", "title": "原有案件"}).json()
    duplicate = transfer(client, a, source)
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "DUPLICATE_CASE_NUMBER"
    assert client.get(f"/api/case-information/{source['id']}/detail", headers=a).json()["version"] == 1
    client.post(f"/api/case-information/{source['id']}/delete", headers=headers(a), json={"version": 1})
    assert transfer(client, a, source).json()["code"] == "INTAKE_HIDDEN"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Case)) == 1
        assert db.scalar(select(func.count()).select_from(IntakeCaseLink)) == 0


def test_audit_failure_rolls_back_source_case_and_link(context):
    client, factory = context; a = auth(client, "alice"); source = intake(client, a)
    engine = factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(text("CREATE TRIGGER fail_transfer_audit BEFORE INSERT ON audit_events WHEN NEW.action='INTAKE_CASE_LINK' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END"))
    with TestClient(app, raise_server_exceptions=False) as safe:
        assert transfer(safe, a, source).status_code == 500
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Case)) == 0
        assert db.scalar(select(func.count()).select_from(IntakeCaseLink)) == 0
        assert db.get(CaseInformation, source["id"]).version == 1


def test_two_intakes_can_share_a_case_and_page_links_use_one_query(context):
    client, factory = context; a = auth(client, "alice")
    first, second = intake(client, a, "A-1"), intake(client, a, "A-2")
    case = transfer(client, a, first).json()
    assert transfer(client, a, second, {"source_version": 1, "mode": "EXISTING", "case_id": case["id"], "basis": "同案件来源"}).status_code == 201
    from sqlalchemy import event
    engine = factory.kw["bind"]
    queries = []
    def capture(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        client.post("/api/case-information/search", headers=a, json={"summary_only": True, "include_summary": False})
        original_count = len(queries); queries.clear()
        found = client.post("/api/case-information/search", headers=a, json={"include_case_links": True, "summary_only": True, "include_summary": False}).json()
        assert len(queries) == original_count + 1
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(found["items"]) == 2 and {row["case_link"]["id"] for row in found["items"]} == {case["id"]}
    assert client.get(f"/api/cases/{case['id']}/intake-sources?page_size=1", headers=a).json()["total"] == 2
