from datetime import date


ICD_BENCHMARK = {
    "J06.9": 65.0,
    "J18.9": 180.0,
    "A90": 220.0,
    "E11": 90.0,
    "I10": 80.0,
}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def predict_denial(claim: dict, clinic_fraud_history_count: int = 0) -> dict:
    total = float(claim.get("total_amount_myr") or 0.0)
    icd = (claim.get("icd10_code") or claim.get("primary_diagnosis_code") or "").upper()
    benchmark = float(ICD_BENCHMARK.get(icd, 100.0))
    amount_ratio = (total / benchmark) if benchmark > 0 else 1.0

    try:
        visit = date.fromisoformat(claim.get("visit_date"))
        filing = date.fromisoformat(claim.get("filing_date")) if claim.get("filing_date") else date.today()
        filing_days = max(0, (filing - visit).days)
    except Exception:
        filing_days = 7

    evidence_attached = 1 if claim.get("_evidence_attached") or claim.get("_parsed_evidence") else 0
    icd_risk_tier = 2 if icd.startswith("C") else (1 if icd in ("J18.9", "A90") else 0)

    # Deterministic weighted heuristic (serverless-friendly).
    score = 0.08
    score += _clamp((amount_ratio - 1.0) / 2.0, 0.0, 0.30)
    score += _clamp((filing_days - 7) / 30.0, 0.0, 0.20)
    score += 0.15 if evidence_attached == 0 else 0.0
    score += _clamp(float(clinic_fraud_history_count) * 0.03, 0.0, 0.20)
    score += 0.10 if icd_risk_tier == 2 else (0.05 if icd_risk_tier == 1 else 0.0)
    prob = round(_clamp(score), 3)

    factors = []
    if amount_ratio > 1.5:
        factors.append("amount_ratio")
    if filing_days > 14:
        factors.append("filing_days")
    if evidence_attached == 0:
        factors.append("evidence_attached")
    if clinic_fraud_history_count > 0:
        factors.append("clinic_fraud_history_count")
    if icd_risk_tier > 0:
        factors.append("icd_risk_tier")
    if not factors:
        factors = ["baseline_low_risk"]

    return {
        "denial_probability": prob,
        "risk_level": "HIGH" if prob >= 0.7 else ("MEDIUM" if prob >= 0.4 else "LOW"),
        "top_risk_factors": factors[:3],
        "features": {
            "amount_ratio": round(amount_ratio, 3),
            "filing_days": filing_days,
            "evidence_attached": evidence_attached,
            "clinic_fraud_history_count": clinic_fraud_history_count,
            "icd_risk_tier": icd_risk_tier,
        },
    }

