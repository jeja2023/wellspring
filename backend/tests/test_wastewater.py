from decimal import Decimal
import pytest
from sqlalchemy import select, text
from wellspring.models import Audit, User
from wellspring.security import password_hash
from wellspring.wastewater_models import WastewaterResultEvent
from test_workflow import context, auth, headers


def prepare(context):
    client, factory = context
    with factory() as db:
        alice = db.scalar(select(User).where(User.username == "alice"))
        db.add(User(username="reviewer", org_id=alice.org_id, password_hash=password_hash("test-password-123"))); db.commit()
    return client, factory, auth(client, "alice"), auth(client, "bob"), auth(client, "reviewer")


def site(client, actor, code="SITE-1"):
    return client.post("/api/wastewater/sites", headers=headers(actor), json={"code": code, "name": "合成点位", "district": "合成区域"})


def sample(client, actor, identity, code="SAMPLE-1", quality="VALID"):
    return client.post("/api/wastewater/samples", headers=headers(actor), json={"site_id": identity, "code": code,
        "sampled_at": "2026-11-10T08:00:00+08:00", "sampling_method": "COMPOSITE", "collector": "合成采样员", "flow_m3_day": "100.000001", "quality": quality, "note": "合成质量说明"})


def fields(**overrides):
    return {"analyte": "合成指标", "detection": "QUANTIFIED", "concentration": "12.123456", "quantification_limit": "1.000000",
            "laboratory": "合成实验室", "analysis_method": "合成方法", "report_number": "REPORT-1", **overrides}


def search(client, actor, area, **body):
    response = client.post(f"/api/wastewater/{area}/search", headers=actor, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_scope_idempotency_pagination_and_disabled_site(context):
    client, _, a, b, _ = prepare(context)
    assert site(client, {}, "PRIVATE").status_code == 401
    key = headers(a); body = {"code": "A", "name": "合成点位", "district": "区域"}
    first = client.post("/api/wastewater/sites", headers=key, json=body)
    assert first.status_code == 201
    assert client.post("/api/wastewater/sites", headers=key, json=body).json() == first.json()
    assert site(client, a, "A").status_code == 409
    assert site(client, b, "A").status_code == 201
    assert search(client, b, "sites")["total"] == 1
    assert site(client, a, "B").status_code == 201
    assert len(search(client, a, "sites", page_size=1)["items"]) == 1
    identity = first.json()["id"]
    assert sample(client, b, identity).status_code == 404
    disabled = client.post(f"/api/wastewater/sites/{identity}/state", headers=headers(a), json={"version": 1, "active": False, "reason": "合成停用"})
    assert disabled.status_code == 200
    assert sample(client, a, identity).status_code == 409
    assert search(client, a, "samples")["total"] == 0


def test_result_review_return_update_and_history(context):
    client, factory, a, b, r = prepare(context)
    point = site(client, a).json(); bottle = sample(client, a, point["id"]).json()
    body = {"sample_id": bottle["id"], **fields()}; key = headers(a)
    result = client.post("/api/wastewater/results", headers=key, json=body)
    assert result.status_code == 201
    assert client.post("/api/wastewater/results", headers=key, json=body).json() == result.json()
    assert client.post("/api/wastewater/results", headers=headers(a), json=body).status_code == 409
    assert client.post("/api/wastewater/results", headers=headers(a), json={**body, "laboratory": "另一合成实验室"}).status_code == 201
    identity = result.json()["id"]
    assert search(client, b, "results")["total"] == 0
    route = f"/api/wastewater/results/{identity}/review"
    assert client.post(route, headers=headers(b), json={"version": 1, "action": "CONFIRM", "note": "x"}).status_code == 404
    assert client.post(route, headers=headers(a), json={"version": 1, "action": "CONFIRM", "note": "x"}).status_code == 403
    assert client.post(route, headers=headers(r), json={"version": 1, "action": "RETURN", "note": "补充说明"}).json()["state"] == "RETURNED"
    assert client.post(f"/api/wastewater/results/{identity}/update", headers=headers(r), json={"version": 2, "fields": fields()}).status_code == 403
    updated = client.post(f"/api/wastewater/results/{identity}/update", headers=headers(a), json={"version": 2, "fields": fields(note="合成修订")})
    assert updated.status_code == 200 and updated.json()["version"] == 3
    assert client.post(route, headers=headers(r), json={"version": 1, "action": "CONFIRM", "note": "旧版本"}).status_code == 409
    confirmed = client.post(route, headers=headers(r), json={"version": 3, "action": "CONFIRM", "note": "核对合成报告"})
    assert confirmed.json()["state"] == "REVIEWED"
    assert client.post(f"/api/wastewater/results/{identity}/update", headers=headers(a), json={"version": 4, "fields": fields()}).status_code == 409
    events = client.get(f"/api/wastewater/results/{identity}/events", headers=a).json()["items"]
    assert {event["action"] for event in events} == {"CREATE", "RETURN", "UPDATE", "CONFIRM"}
    with factory() as db:
        assert db.scalar(select(Audit).where(Audit.action == "WASTEWATER_RESULT_REVIEW"))


@pytest.mark.parametrize("values", [fields(concentration="-1"), fields(detection="NOT_DETECTED", concentration="0"), fields(detection="BELOW_LOQ", concentration=None, quantification_limit=None), fields(concentration="0.5"), fields(concentration="0.0000001"), fields(concentration="NaN")])
def test_invalid_measurements_are_rejected(context, values):
    client, _, a, _, _ = prepare(context)
    point = site(client, a).json(); bottle = sample(client, a, point["id"]).json()
    assert client.post("/api/wastewater/results", headers=headers(a), json={"sample_id": bottle["id"], **values}).status_code == 422


def test_trends_use_reviewed_quality_valid_comparable_data_and_never_zero_fill(context):
    client, _, a, b, reviewer = prepare(context)
    point = site(client, a).json()
    for index, (quality, detection, reviewed, method) in enumerate([
        ("VALID", "QUANTIFIED", True, "合成方法"), ("VALID", "NOT_DETECTED", True, "合成方法"),
        ("FLAGGED", "QUANTIFIED", True, "合成方法"), ("VALID", "QUANTIFIED", False, "合成方法"),
        ("VALID", "QUANTIFIED", True, "其他方法"), ("VALID", "BELOW_LOQ", True, "合成方法")]):
        bottle = sample(client, a, point["id"], f"S-{index}", quality).json()
        row = client.post("/api/wastewater/results", headers=headers(a), json={"sample_id": bottle["id"], **fields(detection=detection, concentration="12.123456" if detection == "QUANTIFIED" else None, analysis_method=method)}).json()
        if reviewed:
            assert client.post(f"/api/wastewater/results/{row['id']}/review", headers=headers(reviewer), json={"version": 1, "action": "CONFIRM", "note": "测试核对"}).status_code == 200
    body = {"site_id": point["id"], "analyte": "合成指标", "laboratory": "合成实验室", "analysis_method": "合成方法", "sampling_method": "COMPOSITE", "start_date": "2026-11-10", "end_date": "2026-11-10"}
    assert client.post("/api/wastewater/trends/search", headers=b, json=body).status_code == 404
    response = client.post("/api/wastewater/trends/search", headers=a, json=body)
    assert response.status_code == 200, response.text
    trend = response.json()
    assert trend["sample_count"] == 3 and trend["quantified_count"] == 1
    assert sum(point["concentration"] is None for point in trend["points"]) == 2
    assert Decimal(next(point["concentration"] for point in trend["points"] if point["concentration"])) == Decimal("12.123456")
    assert client.post("/api/wastewater/trends/search", headers=a, json={**body, "end_date": "2026-11-09"}).status_code == 422


def test_result_and_event_roll_back_if_audit_fails(context):
    client, factory, a, _, _ = prepare(context)
    point = site(client, a).json(); bottle = sample(client, a, point["id"]).json()
    engine = factory.kw["bind"]
    with engine.begin() as db:
        db.execute(text("CREATE TRIGGER fail_water_audit BEFORE INSERT ON audit_events WHEN NEW.action='WASTEWATER_RESULT_CREATE' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END"))
    from fastapi.testclient import TestClient
    from wellspring.main import app
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/api/wastewater/results", headers=headers(a), json={"sample_id": bottle["id"], **fields()}).status_code == 500
    with factory() as db:
        assert db.scalar(select(WastewaterResultEvent)) is None


def test_source_unit_and_timezone_are_explicit(context):
    client, _, a, _, _ = prepare(context)
    point = site(client, a).json()
    assert client.post("/api/wastewater/samples", headers=headers(a), json={"site_id": point["id"], "code": "NAIVE",
        "sampled_at": "2026-11-10T08:00:00", "sampling_method": "GRAB", "collector": "测试", "quality": "VALID"}).status_code == 422
    bottle = sample(client, a, point["id"]).json()
    assert client.post("/api/wastewater/results", headers=headers(a), json={"sample_id": bottle["id"], **fields(), "unit": "mg/L"}).status_code == 422


def test_new_module_migration_preserves_existing_database_and_checks_metadata(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    import sqlite3
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "synthetic.db"
    environment = {**os.environ, "DATABASE_URL": "sqlite:///" + database.as_posix()}
    def run(*args):
        response = subprocess.run([sys.executable, *args], cwd=backend, env=environment, capture_output=True, text=True, timeout=120)
        assert response.returncode == 0, response.stdout + response.stderr
    run("-m", "alembic", "upgrade", "0018")
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO organizations (id,name) VALUES ('preserved', '合成历史组织')")
    run("-c", "from pathlib import Path; from wellspring.startup_migrations import upgrade; import os; upgrade(os.environ['DATABASE_URL'], automatic=False, backup_dir=Path('" + tmp_path.as_posix() + "/snapshots'))")
    with sqlite3.connect(database) as connection:
        from wellspring.main import expected_schema_heads
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == tuple(expected_schema_heads())
        assert connection.execute("SELECT name FROM organizations WHERE id='preserved'").fetchone() == ("合成历史组织",)
        assert connection.execute("SELECT count(*) FROM wastewater_sites").fetchone() == (0,)
    assert len(list((tmp_path / "snapshots").glob("*.sqlite3"))) == 1
    run("-m", "alembic", "check")
