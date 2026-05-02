import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "execution"
if str(EXEC) not in sys.path:
    sys.path.insert(0, str(EXEC))

import disposition_engine


def test_identity_mismatch_maps_to_reject_invalid():
    claim = {"filing_date": "2026-05-02", "created_at": "2026-05-02"}
    extracted = {"visit_date": "2026-05-01", "_invoice_base64": "x"}
    cross_ref = {
        "validation_findings": [
            {"severity": "CRITICAL", "type": "IDENTITY_MISMATCH"}
        ]
    }
    eligibility = {"eligible": True}
    out = disposition_engine.evaluate_phase1_disposition(claim, extracted, cross_ref, eligibility, [{}])
    assert out["disposition_class"] == "REJECT_INVALID"
    assert out["mapped_status"] == "DENIED"
    assert out["finalize_now"] is True


def test_timely_filing_exceeded_is_deny_policy():
    claim = {"filing_date": "2026-05-02", "created_at": "2026-05-02"}
    extracted = {"visit_date": "2026-01-01"}
    cross_ref = {"validation_findings": []}
    eligibility = {"eligible": True}
    out = disposition_engine.evaluate_phase1_disposition(claim, extracted, cross_ref, eligibility, [])
    assert out["disposition_class"] == "DENY_POLICY"
    assert any(h["rule_id"] == "TF_LIMIT_001" for h in out["rule_hits"])

