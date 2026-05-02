import random
from datetime import date

from sklearn.ensemble import RandomForestClassifier


ICD_BENCHMARK = {
    "J06.9": 65.0,
    "J18.9": 180.0,
    "A90": 220.0,
    "E11": 90.0,
    "I10": 80.0,
}

FEATURE_NAMES = [
    "amount_ratio",
    "filing_days",
    "evidence_attached",
    "clinic_fraud_history_count",
    "icd_risk_tier",
]

_MODEL = None


def _train():
    global _MODEL
    if _MODEL is not None:
        return
    rng = random.Random(42)
    x = []
    y = []
    for _ in range(500):
        amount_ratio = rng.uniform(0.4, 3.0)
        filing_days = rng.randint(0, 45)
        evidence = rng.randint(0, 1)
        fraud_hist = rng.randint(0, 8)
        icd_tier = rng.randint(0, 2)
        risk = 0.0
        risk += 0.35 if amount_ratio > 1.7 else 0.0
        risk += 0.2 if filing_days > 14 else 0.0
        risk += 0.2 if evidence == 0 else 0.0
        risk += min(0.2, fraud_hist * 0.03)
        risk += icd_tier * 0.05
        denied = 1 if risk >= 0.35 else 0
        x.append([amount_ratio, filing_days, evidence, fraud_hist, icd_tier])
        y.append(denied)
    _MODEL = RandomForestClassifier(n_estimators=120, random_state=42, max_depth=6)
    _MODEL.fit(x, y)


def predict_denial(claim: dict, clinic_fraud_history_count: int = 0) -> dict:
    _train()
    total = float(claim.get("total_amount_myr") or 0.0)
    icd = (claim.get("icd10_code") or claim.get("primary_diagnosis_code") or "").upper()
    benchmark = ICD_BENCHMARK.get(icd, 100.0)
    amount_ratio = total / benchmark if benchmark > 0 else 1.0
    try:
        visit = date.fromisoformat(claim.get("visit_date"))
        filing = date.fromisoformat(claim.get("filing_date")) if claim.get("filing_date") else date.today()
        filing_days = max(0, (filing - visit).days)
    except Exception:
        filing_days = 7
    evidence_attached = 1 if claim.get("_evidence_attached") or claim.get("_parsed_evidence") else 0
    icd_risk_tier = 2 if icd.startswith("C") else (1 if icd in ("J18.9", "A90") else 0)
    vector = [[amount_ratio, filing_days, evidence_attached, clinic_fraud_history_count, icd_risk_tier]]
    prob = float(_MODEL.predict_proba(vector)[0][1])
    importances = list(_MODEL.feature_importances_)
    pairs = sorted(zip(FEATURE_NAMES, importances), key=lambda z: z[1], reverse=True)[:3]
    return {
        "denial_probability": round(prob, 3),
        "risk_level": "HIGH" if prob >= 0.7 else ("MEDIUM" if prob >= 0.4 else "LOW"),
        "top_risk_factors": [p[0] for p in pairs],
        "features": {
            "amount_ratio": round(amount_ratio, 3),
            "filing_days": filing_days,
            "evidence_attached": evidence_attached,
            "clinic_fraud_history_count": clinic_fraud_history_count,
            "icd_risk_tier": icd_risk_tier,
        },
    }

