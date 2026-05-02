import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "execution"
if str(EXEC) not in sys.path:
    sys.path.insert(0, str(EXEC))

import glm_client


def test_fraud_detection_returns_expected_shape_without_live_api(monkeypatch):
    monkeypatch.delenv("ILMU_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "dev")

    out = glm_client.detect_fraud_patterns({"diagnosis": "URTI", "total_amount_myr": 100})
    assert "fraud_risk_score" in out
    assert "risk_level" in out
    assert "recommendation" in out