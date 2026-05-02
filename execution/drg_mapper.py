ICD_TO_DRG = {
    "J06.9": "DRG 371",
    "J18.9": "DRG 193",
    "A90": "DRG 867",
    "E11": "DRG 637",
    "I10": "DRG 305",
    "K29.7": "DRG 392",
    "M54.5": "DRG 552",
    "J45": "DRG 202",
    "N39.0": "DRG 689",
    "R10.9": "DRG 391",
}


def map_icd_to_drg(icd10_code: str) -> dict:
    icd = (icd10_code or "").upper()
    drg = ICD_TO_DRG.get(icd)
    return {
        "icd10_code": icd,
        "drg_code": drg,
        "drg_ready": bool(drg),
    }

