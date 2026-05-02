import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "execution"
if str(EXEC) not in sys.path:
    sys.path.insert(0, str(EXEC))

import eob_generator


def test_eob_approved_uses_eligibility_coverage_and_copay(monkeypatch):
    monkeypatch.setattr(eob_generator.db, "insert_eob", lambda claim_id, result: 1)
    out = eob_generator.generate_eob(
        1,
        {"total_amount_myr": 200},
        {"decision": "APPROVED", "amount_approved_myr": 100},
        {"covered_amount_myr": 150, "copay_myr": 10},
    )
    assert out["covered_amount_myr"] == 150
    assert out["patient_responsibility_myr"] == 60


def test_eob_denied_sets_denial_code(monkeypatch):
    monkeypatch.setattr(eob_generator.db, "insert_eob", lambda claim_id, result: 1)
    out = eob_generator.generate_eob(
        2,
        {"total_amount_myr": 80},
        {"decision": "DENIED", "denial_reason_code": "16", "denial_reason_description": "Missing info"},
        {"copay_myr": 0},
    )
    assert out["denial_code"] == "16"
    assert out["covered_amount_myr"] == 0