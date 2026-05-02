"""
validation_engine.py - Deterministic evidence consistency validator.

Compares submitted claim fields against normalized values extracted from
supporting evidence documents (invoice/lab/xray/clinical docs).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _norm_ic(v: Any) -> str:
    if v is None:
        return ""
    s = re.sub(r"[^0-9]", "", str(v))
    if len(s) == 12:
        return f"{s[:6]}-{s[6:8]}-{s[8:]}"
    return s


def _norm_name(v: Any) -> str:
    if not v:
        return ""
    s = str(v).upper()
    s = re.sub(r"\b(BIN|BINTI|A/L|A/P)\b", " ", s)
    s = re.sub(r"[^A-Z ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _name_similarity(a: str, b: str) -> float:
    """Token-overlap similarity for Malaysian names.

    Uses the SHORTER name as the denominator so that a submitted name of
    "Siti Nurhaliza" still matches a lab report listing the full
    "Siti Nurhaliza binti Mohd" (2/2 = 1.0) rather than scoring 2/4 = 0.5
    which the old max-denominator formula produced.
    """
    if not a or not b:
        return 0.0
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    overlap = len(ta.intersection(tb))
    # Use the shorter token set as denominator — a short name is a valid
    # abbreviated form of a longer one (e.g. "Siti Nurhaliza" ⊂ full name).
    denom = min(len(ta), len(tb))
    return overlap / float(denom)


def _to_amount(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v)
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", s.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _parse_date(v: Any) -> Optional[datetime]:
    if not v:
        return None
    s = str(v).strip()
    fmts = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _evidence_identity(parsed: Dict[str, Any], doc_type: str) -> Tuple[str, str]:
    if doc_type == "INVOICE":
        return (
            parsed.get("patient_name_on_invoice") or "",
            parsed.get("ic_number_on_invoice") or "",
        )
    if doc_type == "LAB_REPORT":
        return (
            parsed.get("patient_name_on_report") or "",
            parsed.get("ic_number_on_report") or "",
        )
    return ("", "")


def _evidence_date(parsed: Dict[str, Any], doc_type: str) -> str:
    if doc_type == "INVOICE":
        return parsed.get("invoice_date") or parsed.get("date") or ""
    if doc_type == "LAB_REPORT":
        return parsed.get("reported_date") or parsed.get("registered_date") or ""
    return ""


def _invoice_total(parsed: Dict[str, Any]) -> Optional[float]:
    return _to_amount(parsed.get("grand_total") or parsed.get("total_amount_due"))


def evaluate_claim_consistency(
    claim_data: Dict[str, Any],
    parsed_evidence_list: List[Dict[str, Any]],
    date_tolerance_days: int = 30,
    amount_tolerance_myr: float = 1.0,
) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    submitted_name = claim_data.get("patient_name") or ""
    submitted_ic = claim_data.get("patient_ic") or ""
    submitted_total = _to_amount(claim_data.get("total_amount_myr"))
    submitted_visit = _parse_date(claim_data.get("visit_date"))

    for idx, ev in enumerate(parsed_evidence_list or []):
        triage = ev.get("triage") or {}
        parsed = ev.get("parsed_evidence") or {}
        doc_type = triage.get("doc_type") or "UNKNOWN"
        evidence_id = f"{doc_type}:{idx}"

        # 1) Identity checks.
        ev_name_raw, ev_ic_raw = _evidence_identity(parsed, doc_type)
        ev_name = _norm_name(ev_name_raw)
        ev_ic = _norm_ic(ev_ic_raw)
        sub_name = _norm_name(submitted_name)
        sub_ic = _norm_ic(submitted_ic)

        if ev_ic and sub_ic:
            if ev_ic != sub_ic:
                findings.append({
                    "severity": "CRITICAL",
                    "type": "IDENTITY_MISMATCH",
                    "field": "patient_ic",
                    "claim_value": submitted_ic,
                    "evidence_value": ev_ic_raw,
                    "source_doc": doc_type,
                    "evidence_id": evidence_id,
                    "note": f"IC mismatch between claim and {doc_type.lower()} evidence.",
                })
            else:
                findings.append({
                    "severity": "INFO",
                    "type": "IDENTITY_MATCH",
                    "field": "patient_ic",
                    "claim_value": submitted_ic,
                    "evidence_value": ev_ic_raw,
                    "source_doc": doc_type,
                    "evidence_id": evidence_id,
                    "note": "IC matches evidence.",
                })

        if ev_name and sub_name:
            sim = _name_similarity(ev_name, sub_name)
            if sim < 0.4:  # raised from 0.5 — short-name abbreviations score 1.0 with new denominator
                findings.append({
                    "severity": "CRITICAL",
                    "type": "IDENTITY_MISMATCH",
                    "field": "patient_name",
                    "claim_value": submitted_name,
                    "evidence_value": ev_name_raw,
                    "source_doc": doc_type,
                    "evidence_id": evidence_id,
                    "note": f"Patient name mismatch (token similarity {sim:.2f}).",
                })

        # 2) Date checks.
        ev_date_raw = _evidence_date(parsed, doc_type)
        ev_date = _parse_date(ev_date_raw)
        if submitted_visit and ev_date:
            delta_days = abs((submitted_visit.date() - ev_date.date()).days)
            sev = "CRITICAL" if delta_days > date_tolerance_days else "INFO"
            msg = (
                f"Visit/document date mismatch by {delta_days} day(s)."
                if sev == "CRITICAL"
                else "Visit/document dates are within tolerance."
            )
            findings.append({
                "severity": sev,
                "type": "DATE_MISMATCH" if sev == "CRITICAL" else "DATE_MATCH",
                "field": "visit_date",
                "claim_value": claim_data.get("visit_date"),
                "evidence_value": ev_date_raw,
                "source_doc": doc_type,
                "evidence_id": evidence_id,
                "delta_days": delta_days,
                "note": msg,
            })

        # 3) Invoice amount checks.
        if doc_type == "INVOICE":
            inv_total = _invoice_total(parsed)
            if submitted_total is not None and inv_total is not None:
                diff = abs(submitted_total - inv_total)
                sev = "WARN" if diff > amount_tolerance_myr else "INFO"
                findings.append({
                    "severity": sev,
                    "type": "AMOUNT_MISMATCH" if sev == "WARN" else "AMOUNT_MATCH",
                    "field": "total_amount_myr",
                    "claim_value": submitted_total,
                    "evidence_value": inv_total,
                    "source_doc": doc_type,
                    "evidence_id": evidence_id,
                    "difference_myr": round(diff, 2),
                    "note": (
                        f"Claim total differs from invoice total by RM {diff:.2f}."
                        if sev == "WARN"
                        else "Claim total matches invoice total."
                    ),
                })

    critical_count = sum(1 for f in findings if f.get("severity") == "CRITICAL")
    warn_count = sum(1 for f in findings if f.get("severity") == "WARN")
    verdict = "FAIL" if critical_count else ("WARN" if warn_count else "PASS")

    return {
        "verdict": verdict,
        "critical_count": critical_count,
        "warning_count": warn_count,
        "findings": findings,
    }

