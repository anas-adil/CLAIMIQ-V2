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
    scenarios = [
        {
            "status": "APPROVED",
            "lifecycle_stage": "APPROVED",
            "patient_ic": "900101-14-5566",
            "patient_name": "Ahmad bin Ibrahim",
            "visit_date": today,
            "diagnosis_codes": json.dumps(["J06.9"]),
            "line_items": json.dumps([{"description": "Consultation", "quantity": 1, "unit_price": 45, "total": 45}]),
            "total_amount_myr": 45.0,
            "fraud_score": 0.05,
            "fraud_level": "LOW",
        },
        {
            "status": "FRAUD_FLAG",
            "lifecycle_stage": "FRAUD_FLAG",
            "patient_ic": "850212-10-1234",
            "patient_name": "Tan Wei Ming",
            "visit_date": today,
            "diagnosis_codes": json.dumps(["A90"]),
            "line_items": json.dumps([{"description": "IV Drip", "quantity": 5, "unit_price": 100, "total": 500}]),
            "total_amount_myr": 500.0,
            "fraud_score": 0.85,
            "fraud_level": "CRITICAL",
        },
        {
            "status": "PENDING_RAI",
            "lifecycle_stage": "PENDING_RAI",
            "patient_ic": "921105-01-4455",
            "patient_name": "Siti Nurhaliza",
            "visit_date": today,
            "diagnosis_codes": json.dumps(["M54.5"]),
            "line_items": json.dumps([{"description": "Physiotherapy", "quantity": 1, "unit_price": 150, "total": 150}]),
            "total_amount_myr": 150.0,
            "fraud_score": 0.15,
            "fraud_level": "LOW",
        },
        {
            "status": "DENIED",
            "lifecycle_stage": "DENIED",
            "patient_ic": "900101-14-5566",
            "patient_name": "Ahmad bin Ibrahim",
            "visit_date": today,
            "diagnosis_codes": json.dumps(["J06.9"]),
            "line_items": json.dumps([{"description": "Consultation", "quantity": 1, "unit_price": 45, "total": 45}]),
            "total_amount_myr": 45.0,
            "fraud_score": 0.05,
            "fraud_level": "LOW",
            "reasoning": "Duplicate claim detected against claim 1",
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
             clinic_id, "Klinik Alpha Demo", "Seeded demo diagnosis", json.loads(sc["diagnosis_codes"])[0],
             sc["diagnosis_codes"], sc["line_items"], sc["total_amount_myr"])
        )
        cid = cur.lastrowid
        inserted += 1
        
        # Add fraud score
        conn.execute("INSERT INTO fraud_scores (claim_id, risk_score, risk_level, flags, recommendation) VALUES (?, ?, ?, ?, ?)",
                     (cid, sc["fraud_score"], sc["fraud_level"], json.dumps([]), "REVIEW" if sc["fraud_level"] == "CRITICAL" else "PROCEED"))
                     
        # Add decision if approved/denied
        if sc["status"] in ("APPROVED", "DENIED"):
            conn.execute("INSERT INTO decisions (claim_id, decision, confidence, reasoning, amount_approved_myr, amount_denied_myr, is_final) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (cid, sc["status"], 0.95, sc.get("reasoning", "Standard approval"), sc["total_amount_myr"] if sc["status"]=="APPROVED" else 0, sc["total_amount_myr"] if sc["status"]=="DENIED" else 0, 1))
            
            # Add mock advisory
            conn.execute("INSERT INTO advisories (claim_id, summary, summary_bm, action_items) VALUES (?, ?, ?, ?)",
                         (cid, f"AI Advisory for {sc['patient_name']}: {sc['status']} based on policy rules.", 
                          f"Nasihat AI untuk {sc['patient_name']}: {sc['status']} berdasarkan peraturan polisi.",
                          json.dumps([{"action": "Maintain record", "priority": "LOW"}])))
            
            # Add mock EOB
            conn.execute("INSERT INTO eobs (claim_id, billed_amount_myr, covered_amount_myr, patient_responsibility_myr, eob_text) VALUES (?, ?, ?, ?, ?)",
                         (cid, sc["total_amount_myr"], sc["total_amount_myr"] if sc["status"]=="APPROVED" else 0, 
                          0 if sc["status"]=="APPROVED" else sc["total_amount_myr"], f"EOB generated for {sc['patient_name']}."))
                         
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
