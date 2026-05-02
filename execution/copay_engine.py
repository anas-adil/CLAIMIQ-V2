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
    pct = total * 0.05
    deductible_floor = 500.0
    copay = min(total, max(pct, min(deductible_floor, total)))
    return {"copay_myr": round(copay, 2), "rule": "BNM_5PCT_OR_RM500", "is_exempt": False, "reason": "Standard 5% co-payment applied."}

