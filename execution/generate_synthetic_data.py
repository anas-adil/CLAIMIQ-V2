import sys, os, json, logging, bcrypt, uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import database as db

logger = logging.getLogger("claimiq.synth")

def seed_hackathon_demo():
    conn = db.get_db()

    # 1. Ensure baseline tenants/users exist (non-destructive, idempotent)
    demo_emails = ['clinic@demo.my', 'processor@demo.my', 'fraud@demo.my', 'admin@demo.my']

    # Simple hash for "Demo@123"
    pwd_hash = bcrypt.hashpw(b"Demo@123", bcrypt.gensalt(12)).decode('utf-8')

    clinic_id = "clinic-alpha"
    tpa_id = "tpa-omega"

    conn.execute(
        "INSERT OR IGNORE INTO clinics (id, name, moh_reg_number) VALUES (?, ?, ?)",
        (clinic_id, "Klinik Alpha Demo", "MOH-123"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO tpas (id, name, license_number, contact_email) VALUES (?, ?, ?, ?)",
        (tpa_id, "Omega TPA Services", "LIC-TPA", "contact@omega.my"),
    )

    demo_users = [
        ("clinic@demo.my", "Clinic Admin", "CLINIC_USER", "CLINIC", clinic_id, None),
        ("processor@demo.my", "Processor Admin", "TPA_PROCESSOR", "TPA", None, tpa_id),
        ("fraud@demo.my", "Fraud Admin", "TPA_FRAUD_ANALYST", "TPA", None, tpa_id),
        ("admin@demo.my", "System Admin", "SYSTEM_ADMIN", "SYSTEM", None, None),
    ]
    for email, full_name, role, tenant_type, c_id, t_id in demo_users:
        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, full_name, role, tenant_type, clinic_id, tpa_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, email, pwd_hash, full_name, role, tenant_type, c_id, t_id),
            )

    clinic_user = conn.execute("SELECT id FROM users WHERE email=?", ("clinic@demo.my",)).fetchone()
    clinic_user_id = clinic_user["id"] if clinic_user else None

    # 2. Seed 4 baseline scenarios only if missing (preserve existing data)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Diagnosis-specific data for rich seeded scenarios
    _DIAG_DATA = {
        "J06.9": {"name": "Acute Upper Respiratory Tract Infection", "limit": 80},
        "A90": {"name": "Dengue Fever", "limit": 500},
        "M54.5": {"name": "Low Back Pain", "limit": 150},
        "I10": {"name": "Essential Hypertension", "limit": 150},
        "E11": {"name": "Type 2 Diabetes Mellitus", "limit": 180},
        "K29.7": {"name": "Gastritis", "limit": 80},
    }

    scenarios = [
        {
            "status": "APPROVED",
            "lifecycle_stage": "APPROVED",
            "patient_ic": "900101-14-5566",
            "patient_name": "Ahmad bin Ibrahim",
            "visit_date": today,
            "diagnosis": "Acute Upper Respiratory Tract Infection",
            "icd10_code": "J06.9",
            "diagnosis_codes": json.dumps(["J06.9"]),
            "line_items": json.dumps([
                {"description": "GP Consultation", "quantity": 1, "unit_price": 35, "total": 35},
                {"description": "Paracetamol 500mg x20", "quantity": 1, "unit_price": 5, "total": 5},
                {"description": "Loratadine 10mg x7", "quantity": 1, "unit_price": 5, "total": 5},
            ]),
            "total_amount_myr": 45.0,
            "fraud_score": 0.05,
            "fraud_level": "LOW",
            "decision_reasoning": (
                "The claim for Ahmad bin Ibrahim presenting with Acute URTI (J06.9) at Klinik Alpha Demo has been reviewed. "
                "The billed amount of RM 45.00 is within the expected range for this diagnosis (guideline: RM 80.00). "
                "Medications prescribed (Paracetamol, Loratadine) are appropriate first-line treatments for URTI symptoms. "
                "The consultation fee of RM 35.00 aligns with the PMCare Fee Schedule for standard GP consultations."
            ),
            "decision_confidence": 0.94,
            "advisory_summary": (
                "GP Advisory: This URTI claim has been processed (APPROVED). "
                "Standard symptomatic management with antipyretics and antihistamines is appropriate. "
                "Advise patient to return if symptoms persist beyond 7 days or worsen significantly. "
                "Documentation is complete — no further action required."
            ),
            "advisory_summary_bm": (
                "Nasihat GP: Tuntutan URTI ini telah diproses (DILULUSKAN). "
                "Pengurusan simptomatik standard dengan antipiretik dan antihistamin adalah sesuai. "
                "Nasihatkan pesakit untuk kembali jika simptom berterusan melebihi 7 hari."
            ),
        },
        {
            "status": "FRAUD_FLAG",
            "lifecycle_stage": "FRAUD_FLAG",
            "patient_ic": "850212-10-1234",
            "patient_name": "Tan Wei Ming",
            "visit_date": today,
            "diagnosis": "Dengue Fever",
            "icd10_code": "A90",
            "diagnosis_codes": json.dumps(["A90"]),
            "line_items": json.dumps([
                {"description": "IV Drip Infusion x5", "quantity": 5, "unit_price": 100, "total": 500},
                {"description": "FBC Panel", "quantity": 1, "unit_price": 45, "total": 45},
                {"description": "GP Consultation", "quantity": 1, "unit_price": 55, "total": 55},
                {"description": "Vitamin B Complex x90", "quantity": 1, "unit_price": 120, "total": 120},
            ]),
            "total_amount_myr": 720.0,
            "fraud_score": 0.85,
            "fraud_level": "CRITICAL",
            "fraud_flags": [
                {"flag_type": "EXCESSIVE_AMOUNT", "description": "Billed amount (RM 720.00) is 1.4x the typical cost for dengue fever (RM 500.00)", "severity": "MEDIUM", "evidence": "Expected: RM 500.00, Actual: RM 720.00"},
                {"flag_type": "PHANTOM_BILLING", "description": "Vitamin B Complex x90 tablets (RM 120) is not a standard treatment for Dengue Fever and appears unjustified", "severity": "HIGH", "evidence": "MOH CPG Dengue does not include Vitamin B as treatment protocol"},
                {"flag_type": "UPCODING", "description": "5x IV drip sessions billed for an outpatient dengue claim — typically 1-2 sessions at GP level", "severity": "HIGH", "evidence": "GP-level dengue management rarely requires 5 IV sessions"},
            ],
            "decision_reasoning": (
                "FRAUD INVESTIGATION REQUIRED: The claim for Tan Wei Ming with Dengue Fever (A90) has been flagged for investigation. "
                "Multiple fraud indicators detected: (1) Vitamin B Complex x90 (RM 120) is not part of MOH CPG Dengue treatment protocol — potential phantom billing. "
                "(2) Five IV drip sessions billed at outpatient GP level is unusual — standard is 1-2 sessions before hospital referral. "
                "(3) Total amount RM 720.00 exceeds typical dengue outpatient claim of ~RM 500.00. "
                "This claim requires manual investigation by the fraud analysis team."
            ),
            "decision_confidence": 0.72,
            "advisory_summary": (
                "GP Advisory: This dengue claim has been FLAGGED for fraud investigation. "
                "Key concerns: (1) Vitamin B Complex is not indicated for dengue — remove from billing. "
                "(2) 5x IV drip sessions at GP level is unusual — if patient required this level of hydration, hospital referral should have been made. "
                "(3) Please provide clinical justification for the treatment intensity."
            ),
            "advisory_summary_bm": (
                "Nasihat GP: Tuntutan denggi ini telah DITANDAKAN untuk siasatan penipuan. "
                "Kebimbangan utama: Vitamin B Complex tidak ditunjukkan untuk denggi. "
                "5 sesi titisan IV di peringkat GP adalah luar biasa."
            ),
        },
        {
            "status": "PENDING_RAI",
            "lifecycle_stage": "PENDING_RAI",
            "patient_ic": "921105-01-4455",
            "patient_name": "Siti Nurhaliza",
            "visit_date": today,
            "diagnosis": "Low Back Pain",
            "icd10_code": "M54.5",
            "diagnosis_codes": json.dumps(["M54.5"]),
            "line_items": json.dumps([
                {"description": "Physiotherapy Session", "quantity": 1, "unit_price": 120, "total": 120},
                {"description": "GP Consultation", "quantity": 1, "unit_price": 30, "total": 30},
            ]),
            "total_amount_myr": 150.0,
            "fraud_score": 0.15,
            "fraud_level": "LOW",
            "decision_reasoning": (
                "The claim for Siti Nurhaliza with Low Back Pain (M54.5) requires additional information. "
                "Physiotherapy referral requires a GP referral letter per PMCare policy. "
                "The billed amount of RM 150.00 is within the expected range for this diagnosis. "
                "Pending: GP referral letter for physiotherapy services."
            ),
            "decision_confidence": 0.88,
        },
        {
            "status": "DENIED",
            "lifecycle_stage": "DENIED",
            "patient_ic": "900101-14-5566",
            "patient_name": "Ahmad bin Ibrahim",
            "visit_date": today,
            "diagnosis": "Acute Upper Respiratory Tract Infection",
            "icd10_code": "J06.9",
            "diagnosis_codes": json.dumps(["J06.9"]),
            "line_items": json.dumps([{"description": "Consultation", "quantity": 1, "unit_price": 45, "total": 45}]),
            "total_amount_myr": 45.0,
            "fraud_score": 0.05,
            "fraud_level": "LOW",
            "decision_reasoning": (
                "DENIED — Duplicate claim detected. A claim for the same patient (IC: 900101-14-5566), "
                "same diagnosis (J06.9 — URTI), same amount (RM 45.00), and same visit date has already been processed and approved. "
                "This appears to be a duplicate submission. CARC Code 18: Duplicate claim/service."
            ),
            "decision_confidence": 0.97,
            "denial_reason_code": "18",
            "denial_reason_description": "Duplicate claim/service",
            "advisory_summary": (
                "GP Advisory: This claim was DENIED as a duplicate. A previous claim for the same patient, visit, "
                "and diagnosis has already been approved. Please review your billing system to prevent duplicate submissions. "
                "If this is a separate visit, ensure the visit date and clinical notes differentiate it clearly."
            ),
            "advisory_summary_bm": (
                "Nasihat GP: Tuntutan ini DITOLAK kerana pendua. Tuntutan sebelumnya untuk pesakit, lawatan, "
                "dan diagnosis yang sama telah diluluskan. Sila semak sistem pengebilan anda."
            ),
        }
    ]
    
    inserted = 0
    for idx, sc in enumerate(scenarios):
        existing_claim = conn.execute(
            "SELECT id FROM claims WHERE clinic_id=? AND patient_ic=? AND visit_date=? AND status=? AND ABS(total_amount_myr-?) < 0.01 LIMIT 1",
            (clinic_id, sc["patient_ic"], sc["visit_date"], sc["status"], sc["total_amount_myr"]),
        ).fetchone()
        if existing_claim:
            continue

        cur = conn.execute(
            "INSERT INTO claims (status, lifecycle_stage, patient_ic, patient_name, visit_date, "
            "clinic_id, clinic_name, diagnosis, icd10_code, diagnosis_codes, line_items, total_amount_myr) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sc["status"], sc["lifecycle_stage"], sc["patient_ic"], sc["patient_name"], sc["visit_date"],
             clinic_id, "Klinik Alpha Demo", sc.get("diagnosis", "Seeded demo diagnosis"), sc.get("icd10_code", json.loads(sc["diagnosis_codes"])[0]),
             sc["diagnosis_codes"], sc["line_items"], sc["total_amount_myr"])
        )
        cid = cur.lastrowid
        inserted += 1
        
        # Add fraud score with proper flags
        fraud_flags = sc.get("fraud_flags", [])
        fraud_rec = "BLOCK" if sc["fraud_level"] == "CRITICAL" else ("INVESTIGATE" if sc["fraud_level"] == "HIGH" else "PROCEED")
        conn.execute("INSERT INTO fraud_scores (claim_id, risk_score, risk_level, flags, recommendation, full_result) VALUES (?, ?, ?, ?, ?, ?)",
                     (cid, sc["fraud_score"], sc["fraud_level"], json.dumps(fraud_flags), fraud_rec,
                      json.dumps({"fraud_risk_score": sc["fraud_score"], "risk_level": sc["fraud_level"], "flags": fraud_flags, "recommendation": fraud_rec})))
                     
        # Add decision with rich reasoning
        if sc["status"] in ("APPROVED", "DENIED", "FRAUD_FLAG"):
            decision_data = {
                "decision": sc["status"],
                "confidence": sc.get("decision_confidence", 0.95),
                "reasoning": sc.get("decision_reasoning", "Standard adjudication completed."),
                "amount_approved_myr": sc["total_amount_myr"] if sc["status"] == "APPROVED" else 0,
                "amount_denied_myr": sc["total_amount_myr"] if sc["status"] == "DENIED" else 0,
                "denial_reason_code": sc.get("denial_reason_code"),
                "denial_reason_description": sc.get("denial_reason_description"),
                "policy_references": json.dumps(["PMCare Fee Schedule 2024"]),
                "conditions": json.dumps([]),
            }
            conn.execute(
                "INSERT INTO decisions (claim_id, decision, confidence, reasoning, amount_approved_myr, amount_denied_myr, "
                "denial_reason_code, denial_reason_description, policy_references, conditions, is_final, full_result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, decision_data["decision"], decision_data["confidence"], decision_data["reasoning"],
                 decision_data["amount_approved_myr"], decision_data["amount_denied_myr"],
                 decision_data.get("denial_reason_code"), decision_data.get("denial_reason_description"),
                 decision_data["policy_references"], decision_data["conditions"], 1,
                 json.dumps(decision_data))
            )
            
            # Add rich advisory
            adv_summary = sc.get("advisory_summary", f"GP Advisory: Claim for {sc['patient_name']} processed ({sc['status']}). Standard documentation practices recommended.")
            adv_summary_bm = sc.get("advisory_summary_bm", f"Nasihat GP: Tuntutan untuk {sc['patient_name']} diproses ({sc['status']}).")
            conn.execute("INSERT INTO advisories (claim_id, summary, summary_bm, action_items) VALUES (?, ?, ?, ?)",
                         (cid, adv_summary, adv_summary_bm,
                          json.dumps([{"action": "File clinical records", "priority": "LOW"}, {"action": "Review billing accuracy", "priority": "MEDIUM"}])))
            
            # Add detailed EOB
            conn.execute("INSERT INTO eobs (claim_id, billed_amount_myr, covered_amount_myr, patient_responsibility_myr, denial_code, denial_description, eob_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (cid, sc["total_amount_myr"],
                          sc["total_amount_myr"] if sc["status"] == "APPROVED" else 0, 
                          0 if sc["status"] == "APPROVED" else sc["total_amount_myr"],
                          sc.get("denial_reason_code"), sc.get("denial_reason_description"),
                          f"Explanation of Benefits for {sc['patient_name']}: Claim {sc['status']}. Diagnosis: {sc.get('diagnosis', 'N/A')} ({sc.get('icd10_code', 'N/A')}). Billed: RM {sc['total_amount_myr']:.2f}."))
                         
        if sc["status"] == "PENDING_RAI" and clinic_user_id:
            conn.execute("INSERT INTO action_notes (id, claim_id, user_id, action_type, note_text) VALUES (?, ?, ?, ?, ?)",
                         (uuid.uuid4().hex, cid, clinic_user_id, "RAI_REQUEST", "Please provide referral letter for physiotherapy."))

    # 3. Generate 50 more synthetic claims deterministically to populate analytics
    import random
    from datetime import timedelta
    
    conds = [
        {"diagnosis": "Acute URI", "icd": "J06.9", "amount": 45.0},
        {"diagnosis": "Hypertension", "icd": "I10", "amount": 120.0},
        {"diagnosis": "Dengue Fever", "icd": "A90", "amount": 450.0},
        {"diagnosis": "Type 2 Diabetes", "icd": "E11", "amount": 150.0},
        {"diagnosis": "Gastritis", "icd": "K29.7", "amount": 65.0},
    ]
    
    for i in range(50):
        cond = random.choice(conds)
        amt = cond["amount"] * random.uniform(0.8, 1.2)
        days_ago = random.randint(0, 30)
        vdate = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        
        # Decide status: 80% approved, 15% denied, 5% fraud
        rand_val = random.random()
        if rand_val < 0.8:
            status = "APPROVED"
            fraud_score = random.uniform(0.01, 0.2)
            fraud_level = "LOW"
        elif rand_val < 0.95:
            status = "DENIED"
            fraud_score = random.uniform(0.05, 0.4)
            fraud_level = "LOW"
        else:
            status = "FRAUD_FLAG"
            fraud_score = random.uniform(0.8, 0.99)
            fraud_level = "CRITICAL"
            
        # MC logic: ~40% of standard claims have MCs
        is_mc = 1 if random.random() < 0.4 else 0
        mc_days_val = random.randint(1, 3) if is_mc else 0
        
        cur = conn.execute(
            "INSERT INTO claims (status, lifecycle_stage, patient_ic, patient_name, visit_date, "
            "clinic_id, clinic_name, diagnosis, icd10_code, diagnosis_codes, line_items, total_amount_myr, is_mc_issued, mc_days) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (status, status, f"900{i:03d}-10-1234", f"Patient {i}", vdate,
             clinic_id, "Klinik Alpha Demo", cond["diagnosis"], cond["icd"], json.dumps([cond["icd"]]),
             json.dumps([{"description": "Consult", "quantity": 1, "unit_price": amt, "total": amt}]), amt, is_mc, mc_days_val)
        )
        cid = cur.lastrowid
        inserted += 1
        
        conn.execute("INSERT INTO fraud_scores (claim_id, risk_score, risk_level, flags, recommendation) VALUES (?, ?, ?, ?, ?)",
                     (cid, fraud_score, fraud_level, json.dumps([]), "REVIEW" if fraud_level == "CRITICAL" else "PROCEED"))
                     
        if status in ("APPROVED", "DENIED"):
            conn.execute("INSERT INTO decisions (claim_id, decision, confidence, reasoning, amount_approved_myr, amount_denied_myr, is_final) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (cid, status, 0.95, "Auto generated", amt if status=="APPROVED" else 0, amt if status=="DENIED" else 0, 1))
            
            # Add mock advisory
            conn.execute("INSERT INTO advisories (claim_id, summary, summary_bm, action_items) VALUES (?, ?, ?, ?)",
                         (cid, f"Synthetic Advisory: This claim was {status.lower()} following automated ruleset evaluation.", 
                          f"Nasihat Sintetik: Tuntutan ini telah {status.lower()} mengikuti penilaian peraturan automatik.",
                          json.dumps([{"action": "Check documentation", "priority": "MEDIUM"}])))
            
            # Add mock EOB
            conn.execute("INSERT INTO eobs (claim_id, billed_amount_myr, covered_amount_myr, patient_responsibility_myr, eob_text) VALUES (?, ?, ?, ?, ?)",
                         (cid, amt, amt if status=="APPROVED" else 0, 
                          0 if status=="APPROVED" else amt, "Automated EOB generation completed." ))

    # 4. Inject "Patient X" (MC Abuser - Friday Spikes)
    # Generate 5 historical claims for Patient X, all on Fridays, with MCs.
    patient_x_ic = "900505-10-5555"
    patient_x_name = "Patient X (Abuser Profile)"
    for weeks_ago in range(1, 6):
        # Calculate a Friday
        days_ago = (datetime.now().weekday() + 3) % 7 + (weeks_ago * 7) # rough Friday approx
        # Make sure it's actually a Friday (weekday = 4 in python)
        base_date = datetime.now(timezone.utc) - timedelta(days=weeks_ago*7)
        days_to_friday = 4 - base_date.weekday()
        vdate = (base_date + timedelta(days=days_to_friday)).strftime("%Y-%m-%d")
        
        amt = 65.0
        cur = conn.execute(
            "INSERT INTO claims (status, lifecycle_stage, patient_ic, patient_name, visit_date, "
            "clinic_id, clinic_name, diagnosis, icd10_code, diagnosis_codes, line_items, total_amount_myr, is_mc_issued, mc_days) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("APPROVED", "APPROVED", patient_x_ic, patient_x_name, vdate,
             clinic_id, "Klinik Alpha Demo", "Acute URI", "J06.9", json.dumps(["J06.9"]),
             json.dumps([{"description": "Consult", "quantity": 1, "unit_price": amt, "total": amt}]), amt, 1, 2)
        )
        cid = cur.lastrowid
        inserted += 1
        conn.execute("INSERT INTO decisions (claim_id, decision, confidence, reasoning, amount_approved_myr, amount_denied_myr, is_final) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (cid, "APPROVED", 0.99, "Auto generated (historical)", amt, 0, 1))
        conn.execute("INSERT INTO fraud_scores (claim_id, risk_score, risk_level, flags, recommendation) VALUES (?, ?, ?, ?, ?)",
                     (cid, 0.1, "LOW", json.dumps([]), "PROCEED"))

    # Backfill legacy seeded rows created before clinic_name/diagnosis fields were populated.
    conn.execute(
        "UPDATE claims SET clinic_name=COALESCE(clinic_name, ?), diagnosis=COALESCE(diagnosis, ?), "
        "icd10_code=COALESCE(icd10_code, json_extract(diagnosis_codes, '$[0]')) "
        "WHERE clinic_id=?",
        ("Klinik Alpha Demo", "Seeded demo diagnosis", clinic_id),
    )
                         
    conn.commit()
    conn.close()
    return {
        "status": "success",
        "message": "Demo data seeding completed",
        "inserted_claims": inserted,
        "preserved_existing_data": True,
    }

if __name__ == "__main__":
    seed_hackathon_demo()
    print("Seeded successfully!")
