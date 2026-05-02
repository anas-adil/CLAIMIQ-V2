import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "execution"
if str(EXEC) not in sys.path:
    sys.path.insert(0, str(EXEC))

import validation_engine


def test_identity_mismatch_is_critical():
    claim = {
        "patient_name": "Siti Nurhaliza",
        "patient_ic": "880505-10-5555",
        "visit_date": "2014-03-10",
        "total_amount_myr": 1650,
    }
    evidence = [{
        "triage": {"doc_type": "INVOICE"},
        "parsed_evidence": {
            "patient_name_on_invoice": "MUHAMMAD KHUDRI BIN HALIM BASHAH",
            "ic_number_on_invoice": "860101-14-5555",
            "invoice_date": "20/12/2013",
            "grand_total": "RM 1650.00",
        },
    }]
    out = validation_engine.evaluate_claim_consistency(claim, evidence)
    assert out["verdict"] == "FAIL"
    assert any(f["type"] == "IDENTITY_MISMATCH" and f["severity"] == "CRITICAL" for f in out["findings"])


def test_amount_warning_not_critical():
    claim = {
        "patient_name": "Ali",
        "patient_ic": "900101-10-1111",
        "visit_date": "2025-01-01",
        "total_amount_myr": 100.0,
    }
    evidence = [{
        "triage": {"doc_type": "INVOICE"},
        "parsed_evidence": {
            "patient_name_on_invoice": "Ali",
            "ic_number_on_invoice": "900101-10-1111",
            "invoice_date": "2025-01-01",
            "grand_total": "102.00",
        },
    }]
    out = validation_engine.evaluate_claim_consistency(claim, evidence)
    assert out["critical_count"] == 0
    assert any(f["type"] == "AMOUNT_MISMATCH" and f["severity"] == "WARN" for f in out["findings"])

