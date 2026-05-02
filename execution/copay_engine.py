def _is_exempt(icd10_code: str, clinic_name: str = "") -> bool:
    icd = (icd10_code or "").upper()
    clinic = (clinic_name or "").lower()
    if icd.startswith("S") or icd.startswith("T"):
        return True
    if icd.startswith("C"):
        return True
    if "government" in clinic or "kkm" in clinic:
        return True
    return False


def compute_copay(total_amount_myr: float, icd10_code: str = "", clinic_name: str = "", patient_mc_risk: float = 0.0, clinic_mc_risk: float = 0.0) -> dict:
    total = float(total_amount_myr or 0.0)
    
    # 1. Check exemptions (Emergency/Gov)
    if _is_exempt(icd10_code, clinic_name):
        return {"copay_myr": 0.0, "rule": "EXEMPT", "is_exempt": True, "reason": "Standard exemption for trauma/government facilities."}

    # 2. Standard Copay 
    # NOTE: We previously planned to apply a punitive behavioral copay here for MC abusers.
    # However, under the Employment Act 1955, we cannot illegally alter the copay or halt the clinic's payment.
    # The punishment is handled via an HR Alert generated in claims_processor.py.
    # 5% of billed amount, capped at RM 50 floor and RM 500 ceiling.
    # Formula: copay = clamp(5% of total, RM 5, RM 500)
    # Old formula `min(total, max(pct, min(500, total)))` evaluated to `total`
    # for any amount < 500 (i.e. patient always owed the full bill). Fixed below.
    pct = round(total * 0.05, 2)
    copay = max(5.0, min(pct, 500.0))
    copay = min(copay, total)  # never charge more than the bill itself
    return {"copay_myr": round(copay, 2), "rule": "BNM_5PCT_CAPPED_RM500", "is_exempt": False, "reason": "Standard 5% co-payment (min RM 5, max RM 500) applied."}

