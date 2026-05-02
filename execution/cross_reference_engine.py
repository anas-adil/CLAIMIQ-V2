"""
cross_reference_engine.py — Deterministic Evidence Cross-Reference
"""

import logging
import re
import glm_client
import validation_engine

logger = logging.getLogger("claimiq.xref")

def _normalize_name(name: str) -> str:
    if not name: return ""
    name = name.upper()
    name = re.sub(r'\b(BIN|BINTI|A/L|A/P)\b', '', name)
    return re.sub(r'[^A-Z]', '', name)

def check_identity_match(parsed_name: str, submitted_name: str) -> dict:
    if not parsed_name or not submitted_name:
        return {"match": True, "note": "Identity check skipped (missing data)"}
        
    norm_p = _normalize_name(parsed_name)
    norm_s = _normalize_name(submitted_name)
    
    if not norm_p or not norm_s:
        return {"match": True, "note": "Identity check skipped (unparseable names)"}
        
    if norm_s in norm_p or norm_p in norm_s:
        return {"match": True, "note": "Identity matches"}
        
    tokens_p = set(parsed_name.upper().replace('BINTI', '').replace('BIN', '').split())
    tokens_s = set(submitted_name.upper().replace('BINTI', '').replace('BIN', '').split())
    
    overlap = len(tokens_p.intersection(tokens_s))
    if overlap >= max(1, len(tokens_p) // 2) or overlap >= max(1, len(tokens_s) // 2):
         return {"match": True, "note": "Identity matches (partial)"}
         
    return {"match": False, "note": f"Mismatch: '{parsed_name}' vs '{submitted_name}'"}

def extract_number(text: str):
    if text is None: return None
    if isinstance(text, (int, float)): return float(text)
    match = re.search(r"(\d+(\.\d+)?)", str(text))
    return float(match.group(1)) if match else None

def _find_value_near_keyword(text: str, keywords: list, window: int = 200) -> float:
    """
    Search for a numeric value mentioned near any of the given keywords
    in the text. Uses a context window approach: find each keyword occurrence,
    then look for numbers within `window` characters after it.
    Returns the first matching number, or None.
    """
    text_lower = text.lower()
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text_lower):
            # Extract the text window after the keyword
            start = m.end()
            end = min(start + window, len(text_lower))
            snippet = text_lower[start:end]
            # Find the first standalone number in the window
            num_match = re.search(r'(?<![a-z])(\d+(?:[,.]\d+)?)(?:\s*(?:x\s*10|×\s*10|x10))?', snippet)
            if num_match:
                val = extract_number(num_match.group(1))
                if val is not None and val > 0:
                    return val
    return None


def check_lab_vs_description(parsed_results: list, doctor_description: str) -> list:
    """Dynamically compare every Gemini-parsed lab result against the doctor's notes.

    No hardcoded test names — works for any panel Gemini returns. For each result:
    1. Tokenise the test name into search keywords.
    2. Check whether those keywords appear in the doctor's text.
    3. If a numeric value is found near those keywords, compare it to the lab value.
    4. Flag >50% discrepancy as CRITICAL_CONTRADICTION.
    """
    checks = []
    if not doctor_description or not parsed_results:
        return checks

    doc_lower = doctor_description.lower()

    for res in parsed_results:
        test_name = (res.get("test") or "").strip()
        lab_val = extract_number(res.get("value"))
        flag = str(res.get("flag") or "").upper()
        unit = (res.get("unit") or "").strip()
        ref_range = str(res.get("ref_range") or res.get("reporting_limit") or "")

        if not test_name or lab_val is None:
            continue

        # Build search tokens from the test name — split on common delimiters,
        # keep tokens longer than 2 chars so short abbreviations still work.
        tokens = [t.lower() for t in re.split(r"[\s\-/()\[\],]+", test_name) if len(t) > 2]
        if not tokens:
            continue

        # Only proceed if the doctor actually mentions this test.
        if not any(tok in doc_lower for tok in tokens):
            continue

        # Find the numeric value the doctor wrote near the test keywords.
        doc_val = _find_value_near_keyword(doc_lower, tokens)
        if doc_val is None:
            continue

        # Scale-normalise: handle e.g. platelets written as 15 vs lab value 15 000.
        compare_doc, compare_lab = doc_val, lab_val
        if compare_doc > 1000 and compare_lab < 1000:
            compare_doc /= 1000
        elif compare_lab > 1000 and compare_doc < 1000:
            compare_lab /= 1000

        diff = abs(compare_doc - compare_lab)
        baseline = max(compare_doc, compare_lab, 1e-9)
        if diff / baseline > 0.5:
            flag_label = "ELEVATED" if flag in ("H", "ELEVATED", "HIGH", "ABOVE") else "discrepant"
            ref_str = f", limit {ref_range}" if ref_range else ""
            checks.append({
                "check": "lab_vs_description",
                "result": "CRITICAL_CONTRADICTION",
                "field": test_name,
                "doctor_says": f"{doc_val} {unit}".strip(),
                "lab_shows": f"{lab_val} {unit} ({flag_label}{ref_str})".strip(),
                "note": (
                    f"⚠️ FRAUD ALERT: Doctor stated {test_name} ≈ {doc_val} {unit}, "
                    f"but lab report shows {lab_val} {unit} ({flag_label}{ref_str}). "
                    f"Discrepancy: {diff / baseline * 100:.0f}%."
                ),
            })

    return checks

def check_invoice_vs_claim(parsed_invoice: dict, claimed_amount: float) -> dict:
    if not parsed_invoice or claimed_amount is None:
        return None
        
    grand_total = extract_number(parsed_invoice.get("grand_total"))
    if grand_total is not None and claimed_amount > 0:
        if abs(grand_total - claimed_amount) > 1.0: # RM 1 tolerance
            return {
                "check": "invoice_total",
                "result": "WARN",
                "field": "Total Amount",
                "doctor_says": claimed_amount,
                "invoice_shows": grand_total,
                "note": f"Claimed amount (RM {claimed_amount}) differs from invoice total (RM {grand_total})."
            }
    return None

def cross_reference_all(parsed_evidence_list: list, claim_data: dict, raw_text: str = "") -> dict:
    if not parsed_evidence_list:
        return {
            "verdict": "UNABLE_TO_VERIFY",
            "checks": [],
            "contradiction_count": 0,
            "critical_count": 0,
            "note": "No valid parsed evidence to cross-reference."
        }
        
    checks = []

    # 0. Deterministic cross-document consistency validation (no LLM dependency).
    deterministic = validation_engine.evaluate_claim_consistency(claim_data, parsed_evidence_list)
    for f in deterministic.get("findings", []):
        sev = f.get("severity", "INFO")
        if sev not in ("WARN", "CRITICAL"):
            continue
        checks.append({
            "check": "deterministic_consistency",
            "result": "CRITICAL_CONTRADICTION" if sev == "CRITICAL" else "WARN",
            "field": f.get("field", "unknown"),
            "doctor_says": f.get("claim_value"),
            "lab_shows": f.get("evidence_value"),
            "note": f.get("note"),
            "evidence_id": f.get("evidence_id"),
            "source_doc": f.get("source_doc"),
            "validation_type": f.get("type"),
        })
    
    # 1. Identity Check (deterministic is fine)
    for parsed_evidence in parsed_evidence_list:
        if not parsed_evidence or parsed_evidence.get("source") in ["NO_EVIDENCE", "PARSE_FAILED"]:
            continue
            
        triage = parsed_evidence.get("triage", {})
        parsed_data = parsed_evidence.get("parsed_evidence", {})
        doc_type = triage.get("doc_type")
        
        submitted_name = claim_data.get("patient_name")
        parsed_name = None
        if doc_type == "LAB_REPORT":
            parsed_name = parsed_data.get("patient_name_on_report")
        elif doc_type == "INVOICE":
            parsed_name = parsed_data.get("patient_name_on_invoice")
            
        if parsed_name and submitted_name:
            id_check = check_identity_match(parsed_name, submitted_name)
            if not id_check["match"]:
                checks.append({
                    "check": "identity",
                    "result": "CRITICAL_CONTRADICTION",
                    "field": "Patient Name",
                    "note": id_check["note"]
                })
    
    # 2a. Deterministic lab-value vs doctor-notes comparison (catches explicit value mismatches
    #     e.g. doctor writes "o-Cresol < 0.50 mg/L" but lab shows 5.0 mg/L ELEVATED).
    for parsed_evidence in parsed_evidence_list:
        if not parsed_evidence or parsed_evidence.get("source") in ["NO_EVIDENCE", "PARSE_FAILED"]:
            continue
        triage = parsed_evidence.get("triage", {})
        parsed_data = parsed_evidence.get("parsed_evidence", {})
        if triage.get("doc_type") == "LAB_REPORT":
            lab_results = parsed_data.get("results", [])
            lab_checks = check_lab_vs_description(lab_results, raw_text)
            checks.extend(lab_checks)

            # 2b. ELEVATED-flag detector: if ANY result is flagged H/ELEVATED/HIGH but
            #     the doctor's notes claim "normal", "within limits", or "below limits".
            doc_lower = (raw_text or "").lower()
            doctor_claims_normal = any(
                phrase in doc_lower
                for phrase in ("normal", "within limit", "below limit", "within range", "no evidence")
            )
            if doctor_claims_normal:
                for res in lab_results:
                    flag = str(res.get("flag") or "").upper()
                    test_name = res.get("test") or "Unknown test"
                    lab_val = res.get("value")
                    ref_range = res.get("ref_range") or res.get("reporting_limit") or "N/A"
                    if flag in ("H", "ELEVATED", "HIGH", "ABOVE"):
                        checks.append({
                            "check": "elevated_vs_normal_claim",
                            "result": "CRITICAL_CONTRADICTION",
                            "field": test_name,
                            "doctor_says": "normal / within limits",
                            "lab_shows": f"{lab_val} (ELEVATED, limit {ref_range})",
                            "note": (
                                f"⚠️ CRITICAL: Doctor's notes state results are normal/below limits, "
                                f"but lab report shows {test_name} = {lab_val} flagged as ELEVATED "
                                f"(reporting limit: {ref_range}). This is a direct contradiction."
                            ),
                        })

    # 3. GLM AI Alignment Check
    try:
        glm_align = glm_client.cross_reference_evidence(parsed_evidence_list, raw_text)
        
        for contra in glm_align.get("contradictory_evidence", []):
            checks.append({
                "check": "ai_evidence_alignment",
                "result": "CRITICAL_CONTRADICTION",
                "field": contra.get("field", "Clinical Evidence"),
                "doctor_says": contra.get("doctor_says", "N/A"),
                "lab_shows": contra.get("evidence_shows", "N/A"),
                "note": f"⚠️ FRAUD ALERT: Doctor stated {contra.get('field')} ~{contra.get('doctor_says')}, but evidence shows {contra.get('evidence_shows')}."
            })
    except Exception as e:
        logger.error(f"GLM Alignment check failed: {e}")
        
    # 4. GLM Invoice Validation
    invoice_list = [ev.get("parsed_evidence", {}) for ev in parsed_evidence_list if ev.get("triage", {}).get("doc_type") == "INVOICE"]
    for inv in invoice_list:
        try:
            glm_inv = glm_client.validate_invoice_against_treatment(inv, raw_text)
            for unjust in glm_inv.get("unjustified_items", []):
                checks.append({
                    "check": "phantom_billing",
                    "result": "CRITICAL_CONTRADICTION",
                    "field": "Invoice Item",
                    "doctor_says": "Not mentioned in clinical notes",
                    "invoice_shows": unjust.get("item_description", "Unknown"),
                    "note": f"⚠️ PHANTOM BILLING: Invoiced item '{unjust.get('item_description')}' (RM {unjust.get('amount')}) is not justified by the doctor's notes. Reason: {unjust.get('reason')}"
                })
        except Exception as e:
            logger.error(f"GLM Invoice check failed: {e}")
        
    critical_count = sum(1 for c in checks if c["result"] == "CRITICAL_CONTRADICTION")
    contradiction_count = len(checks)
    
    verdict = "PASS"
    if critical_count > 0:
        verdict = "FAIL"
    elif contradiction_count > 0:
        verdict = "WARN"
        
    return {
        "verdict": verdict,
        "checks": checks,
        "contradiction_count": contradiction_count,
        "critical_count": critical_count,
        "validation_findings": deterministic.get("findings", []),
        "deterministic_summary": {
            "verdict": deterministic.get("verdict", "PASS"),
            "critical_count": deterministic.get("critical_count", 0),
            "warning_count": deterministic.get("warning_count", 0),
        },
    }
