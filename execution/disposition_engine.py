"""
disposition_engine.py - Deterministic hard-gate disposition logic.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

_DEFAULT_POLICY = {
    "policy_version": "default",
    "timely_filing_days": 14,
    "identity_mismatch_action": "REJECT_INVALID",
    "timely_filing_action": "DENY_POLICY",
    "missing_parse_with_attachment_action": "PEND_REVIEW",
    "status_map": {
        "REJECT_INVALID": "DENIED",
        "DENY_POLICY": "DENIED",
        "PEND_REVIEW": "UNDER_REVIEW",
        "APPROVE": "APPROVED",
    },
    "appealability": {
        "REJECT_INVALID": False,
        "DENY_POLICY": True,
        "PEND_REVIEW": True,
        "APPROVE": False,
    },
}


def load_policy() -> Dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), "policy_config.json")
    if not os.path.exists(path):
        return dict(_DEFAULT_POLICY)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(_DEFAULT_POLICY)
        merged.update(data)
        return merged
    except Exception:
        return dict(_DEFAULT_POLICY)


def _parse_date(v: Any):
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def evaluate_phase1_disposition(
    claim_record: Dict[str, Any],
    extracted: Dict[str, Any],
    cross_ref: Dict[str, Any],
    eligibility: Dict[str, Any],
    parsed_evidence_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    policy = load_policy()
    hits: List[Dict[str, Any]] = []

    # Rule: identity mismatch from deterministic findings.
    findings = cross_ref.get("validation_findings", []) or []
    has_identity_mismatch = any(
        f.get("severity") == "CRITICAL" and f.get("type") == "IDENTITY_MISMATCH"
        for f in findings
    )
    if has_identity_mismatch:
        hits.append({
            "rule_id": "ID_MATCH_001",
            "severity": "CRITICAL",
            "disposition": policy.get("identity_mismatch_action", "REJECT_INVALID"),
            "reason": "Patient identity mismatch across claim and supporting evidence.",
        })

    # Rule: timely filing.
    visit_dt = _parse_date(extracted.get("visit_date") or claim_record.get("visit_date"))
    filing_dt = _parse_date(claim_record.get("filing_date") or claim_record.get("created_at"))
    if visit_dt and filing_dt:
        delta = (filing_dt.date() - visit_dt.date()).days
        if delta > int(policy.get("timely_filing_days", 14)):
            hits.append({
                "rule_id": "TF_LIMIT_001",
                "severity": "CRITICAL",
                "disposition": policy.get("timely_filing_action", "DENY_POLICY"),
                "reason": (
                    f"Timely filing exceeded: {delta} days from visit to filing "
                    f"(limit={policy.get('timely_filing_days', 14)})."
                ),
                "days_late": delta,
            })

    # Rule: attachments declared but not parsed.
    has_declared_attachments = bool(extracted.get("_evidence_base64") or extracted.get("_invoice_base64"))
    if has_declared_attachments and not parsed_evidence_list:
        hits.append({
            "rule_id": "PARSE_001",
            "severity": "CRITICAL",
            "disposition": policy.get("missing_parse_with_attachment_action", "PEND_REVIEW"),
            "reason": "Evidence attachments were declared but parsing did not produce usable evidence.",
        })

    # Eligibility can be a policy denial.
    if eligibility and not eligibility.get("eligible", True):
        hits.append({
            "rule_id": "ELIG_001",
            "severity": "CRITICAL",
            "disposition": "DENY_POLICY",
            "reason": eligibility.get("message", "Eligibility failure."),
            "carc": eligibility.get("carc_code", "27"),
        })

    priority = {"REJECT_INVALID": 4, "DENY_POLICY": 3, "PEND_REVIEW": 2, "APPROVE": 1}
    disposition = "APPROVE"
    if hits:
        disposition = sorted(hits, key=lambda h: priority.get(h.get("disposition"), 0), reverse=True)[0]["disposition"]

    status_map = policy.get("status_map", _DEFAULT_POLICY["status_map"])
    mapped_status = status_map.get(disposition, "UNDER_REVIEW")
    appealable = bool(policy.get("appealability", _DEFAULT_POLICY["appealability"]).get(disposition, True))

    return {
        "policy_version": policy.get("policy_version", "default"),
        "disposition_class": disposition,
        "mapped_status": mapped_status,
        "appealable": appealable,
        "rule_hits": hits,
        "finalize_now": disposition in ("REJECT_INVALID", "DENY_POLICY", "PEND_REVIEW") and len(hits) > 0,
    }

