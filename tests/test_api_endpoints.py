import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "execution"
if str(EXEC) not in sys.path:
    sys.path.insert(0, str(EXEC))

import api_server


def test_metrics_endpoint(monkeypatch):
    monkeypatch.setattr(api_server.db, "get_analytics_summary", lambda: {"total_claims": 10})
    monkeypatch.setattr(api_server.glm_client, "get_token_metrics", lambda: {"total_tokens": 1000, "calls": 8})
    client = TestClient(api_server.app)
    r = client.get("/api/metrics")
    assert r.status_code == 200
    data = r.json()
    assert data["total_tokens"] == 1000
    assert data["avg_tokens_per_claim"] == 100.0


def test_fhir_coverage_eligibility_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_server.eligibility_engine,
        "check_eligibility",
        lambda ic, vd, amt: {"eligible": True, "covered_amount_myr": 120.0, "patient_responsibility_myr": 30.0},
    )
    client = TestClient(api_server.app)
    r = client.post("/api/fhir/coverage-eligibility", json={"ic_number": "900101-14-1234", "visit_date": "2026-04-30", "total_amount_myr": 150})
    assert r.status_code == 200
    body = r.json()
    assert body["resourceType"] == "EligibilityResponse"
    assert body["insurance"][0]["inforce"] is True


def test_mc_patterns_endpoint(monkeypatch):
    payload = {"weekday_distribution": {"Mon": 2, "Fri": 4}, "monday_friday_cluster_score": 6}
    monkeypatch.setattr(api_server.mc_analytics, "get_mc_behavior_patterns", lambda: payload)
    client = TestClient(api_server.app)
    r = client.get("/api/analytics/mc-patterns")
    assert r.status_code == 200
    assert r.json()["monday_friday_cluster_score"] == 6


def test_review_endpoint(monkeypatch):
    class FakeConn:
        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(api_server.db, "get_full_claim", lambda cid: {"id": cid, "status": "PENDING_APPROVAL"})
    updates = {}

    def _update_claim(claim_id, **kwargs):
        updates["claim_id"] = claim_id
        updates.update(kwargs)

    monkeypatch.setattr(api_server.db, "update_claim", _update_claim)
    monkeypatch.setattr(api_server.db, "get_db", lambda: FakeConn())
    monkeypatch.setattr(api_server.db, "log_audit", lambda *args, **kwargs: None)
    client = TestClient(api_server.app)
    r = client.post("/api/claims/10/review", json={"action": "APPROVE", "reason": "looks good"})
    assert r.status_code == 200
    assert updates["status"] == "APPROVED"


def test_export_endpoint(monkeypatch):
    monkeypatch.setattr(api_server.db, "get_full_claim", lambda cid: {"id": cid, "status": "APPROVED"})
    client = TestClient(api_server.app)
    r = client.get("/api/claims/11/export")
    assert r.status_code == 200
    assert r.json()["claim_id"] == 11

