import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "execution"
if str(EXEC) not in sys.path:
    sys.path.insert(0, str(EXEC))

import claim_scrubber


def test_valid_icd_format_accepts_standard_code():
    assert claim_scrubber._valid_icd_format("J18.9")


def test_scrub_claim_fails_when_required_fields_missing():
    result = claim_scrubber.scrub_claim({"raw_text": "test"})
    assert result["status"] == "FAIL"
    assert any(err["check"] == "REQUIRED_FIELD" for err in result["errors"])