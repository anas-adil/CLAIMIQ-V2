import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "execution"
if str(EXEC) not in sys.path:
    sys.path.insert(0, str(EXEC))

import glm_client


def test_deterministic_extract_infers_diagnosis_from_assessment_plan():
    raw = (
        "Name: Siti Nurhaliza\n"
        "IC: 880505-10-5555\n"
        "Clinic: Tanglin Medical Center (Inpatient Wing)\n"
        "Date: 2014-03-10\n"
        "Total: 1650.00\n\n"
        "Assessment & Plan: Acute Dengue Hemorrhagic Fever. "
        "Patient requires immediate transfer to isolation ward.\n"
    )
    data = glm_client._deterministic_extract_from_text(raw)
    assert data["diagnosis"] == "Acute Dengue Hemorrhagic Fever"


def test_mock_chat_never_uses_literal_none_for_diagnosis():
    context = {
        "status": "UNDER_REVIEW",
        "diagnosis": None,
        "decision": {"decision": "UNDER_REVIEW", "reasoning": "Required field missing: diagnosis"},
    }
    prompt = f"## Claim Context\n{json.dumps(context)}\n\n## Question\nwhat does the file say?"
    result = json.loads(glm_client._get_intelligent_mock(glm_client.CHAT_SYSTEM, prompt))
    assert "None" not in result["answer"]
    assert "this visit" in result["answer"]
