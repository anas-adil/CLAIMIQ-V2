import database as db


def get_mc_behavior_patterns() -> dict:
    conn = db.get_db()
    weekday_rows = conn.execute(
        "SELECT strftime('%w', visit_date) AS dow, COUNT(*) c FROM claims "
        "WHERE visit_date IS NOT NULL AND is_mc_issued = 1 GROUP BY dow"
    ).fetchall()
    same_patient = conn.execute(
        "SELECT patient_ic, COUNT(*) c FROM claims WHERE patient_ic IS NOT NULL AND is_mc_issued = 1 "
        "GROUP BY patient_ic HAVING COUNT(*) >= 3 ORDER BY c DESC LIMIT 10"
    ).fetchall()
    same_clinic_day = conn.execute(
        "SELECT clinic_name, visit_date, COUNT(*) c FROM claims WHERE clinic_name IS NOT NULL AND is_mc_issued = 1 "
        "AND visit_date IS NOT NULL GROUP BY clinic_name, visit_date HAVING COUNT(*) >= 4 "
        "ORDER BY c DESC LIMIT 10"
    ).fetchall()
    conn.close()
    labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    dist = {labels[int(r["dow"])]: r["c"] for r in weekday_rows if r["dow"] is not None}
    return {
        "weekday_distribution": dist,
        "monday_friday_cluster_score": (dist.get("Mon", 0) + dist.get("Fri", 0)),
        "frequent_patient_patterns": [dict(r) for r in same_patient],
        "same_day_clinic_spikes": [dict(r) for r in same_clinic_day],
    }

def calculate_patient_mc_risk(patient_ic: str) -> float:
    """
    Calculates MC abuse risk for a patient based on historical claims.
    High risk = frequent MCs on Mondays or Fridays for minor illnesses.
    """
    if not patient_ic:
        return 0.0
    conn = db.get_db()
    rows = conn.execute(
        "SELECT visit_date, icd10_code FROM claims WHERE patient_ic=? AND is_mc_issued=1",
        (patient_ic,)
    ).fetchall()
    conn.close()
    
    if not rows:
        return 0.0
        
    minor_illness_codes = ['J06.9', 'K29.7', 'R51'] # Acute URI, Gastritis, Headache
    risk_score = 0.0
    from datetime import datetime
    
    for r in rows:
        if r['visit_date']:
            try:
                dt = datetime.strptime(r['visit_date'][:10], "%Y-%m-%d")
                if dt.weekday() in (0, 4): # Monday or Friday
                    risk_score += 0.3
                    if r['icd10_code'] in minor_illness_codes:
                        risk_score += 0.2
            except ValueError:
                pass
                
    return min(1.0, risk_score)

def calculate_clinic_mc_risk(clinic_id: str) -> float:
    """
    Calculates if a clinic is an 'MC Mill'.
    High risk = high percentage of claims with MCs for minor illnesses.
    """
    if not clinic_id:
        return 0.0
    conn = db.get_db()
    total_minor = conn.execute(
        "SELECT COUNT(*) FROM claims WHERE clinic_id=? AND icd10_code IN ('J06.9', 'K29.7', 'R51')",
        (clinic_id,)
    ).fetchone()[0]
    
    if total_minor < 5:
        conn.close()
        return 0.0 # Not enough data
        
    mc_minor = conn.execute(
        "SELECT COUNT(*) FROM claims WHERE clinic_id=? AND icd10_code IN ('J06.9', 'K29.7', 'R51') AND is_mc_issued=1",
        (clinic_id,)
    ).fetchone()[0]
    conn.close()
    
    ratio = mc_minor / total_minor
    # If > 80% of minor visits result in MCs, risk goes up
    if ratio > 0.8:
        return min(1.0, (ratio - 0.8) * 5) # scales from 0 to 1
    return 0.0


