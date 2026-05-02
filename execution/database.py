"""
database.py (v2) — Enhanced SQLite schema + data access for ClaimIQ

v2 Upgrades (based on real US TPA standards):
- 10-state claim lifecycle (vs 5 in v1)
- Member eligibility table
- CARC denial reason codes table  
- Analytics fields (ar_days, cycle_time, clean_claim_flag, etc.)
- Appeal tracking
- EOB generation tracking
- Audit timeline per claim
"""

import os
import json
import sqlite3
import logging
import bcrypt
from datetime import datetime, date
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("claimiq.db")

# Serverless runtimes (Vercel/AWS Lambda) have writable temp space at /tmp.
# Prefer /tmp there; use local .tmp path in normal dev unless DB_PATH is set.
if os.getenv("DB_PATH"):
    DB_PATH = os.getenv("DB_PATH")
elif os.getenv("VERCEL") or os.getenv("AWS_REGION") or os.getenv("LAMBDA_TASK_ROOT"):
    DB_PATH = "/tmp/claimiq.db"
else:
    DB_PATH = ".tmp/claimiq.db"
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

# 10-state lifecycle (matches real TPA workflow)
CLAIM_STATES = [
    "INTAKE",           # Claim received
    "SCRUBBING",        # Pre-adjudication validation
    "SCRUB_FAILED",     # Validation failed — returned to provider
    "ELIGIBILITY_CHECK",# Checking member coverage
    "NOT_ELIGIBLE",     # Member not covered
    "PENDING",          # Awaiting adjudication
    "PROCESSING",       # GLM adjudication in progress
    "PENDED",           # On hold — awaiting additional info
    "APPROVED",         # Fully approved
    "DENIED",           # Denied with reason
    "REFERRED",         # Referred for manual review
    "APPEALING",        # Under appeal
    "APPEAL_APPROVED",  # Appeal succeeded
    "APPEAL_DENIED",    # Appeal failed
    "PAID",             # Payment processed
    "CLOSED",           # Case closed
    "ERROR",            # System error
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'INTAKE',
    lifecycle_stage TEXT DEFAULT 'INTAKE',
    raw_text TEXT,
    extracted_data TEXT,
    coded_data TEXT,
    scrub_result TEXT,
    eligibility_result TEXT,

    -- Patient info (denormalized for fast queries)
    patient_name TEXT,
    patient_ic TEXT,
    patient_age INTEGER,
    patient_gender TEXT,
    clinic_name TEXT,
    clinic_id TEXT,
    diagnosis TEXT,
    icd10_code TEXT,
    visit_date TEXT,
    filing_date TEXT DEFAULT (date('now')),
    total_amount_myr REAL,
    consultation_fee_myr REAL,
    medication_fee_myr REAL,
    procedure_fee_myr REAL,

    -- Processing flags
    clean_claim_flag INTEGER DEFAULT 0,
    auto_adjudicated INTEGER DEFAULT 0,
    fraud_flagged INTEGER DEFAULT 0,
    requires_prior_auth INTEGER DEFAULT 0,

    -- MC Tracking & Predictive Risk
    is_mc_issued INTEGER DEFAULT 0,
    mc_days INTEGER DEFAULT 0,
    patient_mc_risk_score REAL DEFAULT 0.0,
    clinic_mc_risk_score REAL DEFAULT 0.0,

    -- Timeline
    intake_at TEXT DEFAULT (datetime('now')),
    scrub_at TEXT,
    eligibility_at TEXT,
    adjudication_at TEXT,
    payment_at TEXT,
    closed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),

    -- Derived KPIs (stored for fast analytics)
    ar_days REAL,
    cycle_time_hours REAL
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT UNIQUE,
    ic_number TEXT UNIQUE,
    name TEXT,
    date_of_birth TEXT,
    gender TEXT,
    plan_id TEXT DEFAULT 'PMC-STANDARD',
    benefit_tier TEXT DEFAULT 'STANDARD',

    -- Coverage
    coverage_start_date TEXT,
    coverage_end_date TEXT,
    is_active INTEGER DEFAULT 1,

    -- Financial responsibility
    annual_deductible_myr REAL DEFAULT 0,
    deductible_met_myr REAL DEFAULT 0,
    copay_myr REAL DEFAULT 10,
    coinsurance_pct REAL DEFAULT 0,
    max_out_of_pocket_myr REAL DEFAULT 500,

    -- Benefit limits
    annual_outpatient_limit_myr REAL DEFAULT 1000,
    outpatient_used_myr REAL DEFAULT 0,
    max_per_visit_myr REAL DEFAULT 200,

    -- Restrictions
    excluded_conditions TEXT DEFAULT '[]',
    waiting_period_conditions TEXT DEFAULT '[]',
    requires_prior_auth_conditions TEXT DEFAULT '[]',

    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER REFERENCES claims(id),
    decision TEXT,
    confidence REAL,
    reasoning TEXT,
    policy_references TEXT,
    amount_approved_myr REAL DEFAULT 0,
    amount_denied_myr REAL DEFAULT 0,
    patient_responsibility_myr REAL DEFAULT 0,
    denial_reason_code TEXT,
    denial_reason_description TEXT,
    conditions TEXT,
    appeal_recommendation TEXT,
    full_result TEXT,
    is_auto_adjudicated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fraud_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER REFERENCES claims(id),
    risk_score REAL,
    risk_level TEXT,
    flags TEXT,
    recommendation TEXT,
    full_result TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS advisories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER REFERENCES claims(id),
    summary TEXT,
    summary_bm TEXT,
    action_items TEXT,
    full_result TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS appeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER REFERENCES claims(id),
    appeal_reason TEXT,
    supporting_evidence TEXT,
    rebuttal_text TEXT,
    rebuttal_bm TEXT,
    appeal_status TEXT DEFAULT 'SUBMITTED',
    appeal_decision TEXT,
    appeal_reasoning TEXT,
    submitted_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS eobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER REFERENCES claims(id),
    billed_amount_myr REAL,
    covered_amount_myr REAL,
    patient_responsibility_myr REAL,
    denial_code TEXT,
    denial_description TEXT,
    eob_text TEXT,
    eob_text_bm TEXT,
    generated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER,
    actor TEXT DEFAULT 'SYSTEM',
    action TEXT,
    from_status TEXT,
    to_status TEXT,
    details TEXT,
    data_classification TEXT DEFAULT 'SYNTHETIC_PDPA_LOW',
    retention_period TEXT DEFAULT '7Y',
    data_minimization_applied INTEGER DEFAULT 1,
    consent_basis TEXT DEFAULT 'CONTRACTUAL_NECESSITY',
    cross_border_transfer TEXT DEFAULT 'AP-SOUTHEAST-1',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS carc_codes (
    code TEXT PRIMARY KEY,
    description TEXT,
    category TEXT
);

-- Insert standard CARC codes (Malaysian TPA equivalents)
INSERT OR IGNORE INTO carc_codes VALUES ('1', 'Deductible amount', 'Patient Responsibility');
INSERT OR IGNORE INTO carc_codes VALUES ('2', 'Coinsurance amount', 'Patient Responsibility');
INSERT OR IGNORE INTO carc_codes VALUES ('4', 'The service/drug/supply is not covered', 'Coverage');
INSERT OR IGNORE INTO carc_codes VALUES ('5', 'The procedure code is inconsistent with the modifier', 'Coding');
INSERT OR IGNORE INTO carc_codes VALUES ('6', 'The service is not covered when performed with this diagnosis', 'Coverage');
INSERT OR IGNORE INTO carc_codes VALUES ('11', 'The diagnosis is inconsistent with the procedure', 'Coding');
INSERT OR IGNORE INTO carc_codes VALUES ('15', 'Payment adjusted because the submitted procedure code was not appropriate', 'Coding');
INSERT OR IGNORE INTO carc_codes VALUES ('16', 'Claim/service lacks information', 'Documentation');
INSERT OR IGNORE INTO carc_codes VALUES ('18', 'Duplicate claim/service', 'Integrity');
INSERT OR IGNORE INTO carc_codes VALUES ('19', 'Claim is under investigation', 'Fraud');
INSERT OR IGNORE INTO carc_codes VALUES ('22', 'Coordination of benefits', 'COB');
INSERT OR IGNORE INTO carc_codes VALUES ('27', 'Expenses incurred after coverage terminated', 'Eligibility');
INSERT OR IGNORE INTO carc_codes VALUES ('29', 'Filing deadline exceeded (>14 days)', 'Timely Filing');
INSERT OR IGNORE INTO carc_codes VALUES ('45', 'Charge exceeds fee schedule/maximum allowable', 'Amount');
INSERT OR IGNORE INTO carc_codes VALUES ('50', 'Non-covered service', 'Coverage');
INSERT OR IGNORE INTO carc_codes VALUES ('97', 'Claim/service denied — not covered by benefit plan', 'Coverage');
INSERT OR IGNORE INTO carc_codes VALUES ('109', 'Claim/service not covered by this payer', 'Coverage');
INSERT OR IGNORE INTO carc_codes VALUES ('B7', 'Provider not eligible for this plan', 'Provider');
INSERT OR IGNORE INTO carc_codes VALUES ('MA130', 'Patient cannot be identified as insured', 'Eligibility');
"""


_SCHEMA_INITIALIZED = False


def _ensure_demo_users(conn: sqlite3.Connection):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchall()
    if not rows:
        return
    pwd_hash = bcrypt.hashpw(b"Demo@123", bcrypt.gensalt(12)).decode("utf-8")
    demo_users = [
        ("usr-admin", "admin@demo.my", "System Admin", "SYSTEM_ADMIN", "SYSTEM", None, None),
        ("usr-clinic", "clinic@demo.my", "Clinic User", "CLINIC_USER", "CLINIC", "CLINIC-ALPHA", None),
        ("usr-proc", "processor@demo.my", "TPA Processor", "TPA_PROCESSOR", "TPA", None, "TPA-DEMO"),
        ("usr-fraud", "fraud@demo.my", "Fraud Analyst", "TPA_FRAUD_ANALYST", "TPA", None, "TPA-DEMO"),
    ]
    for uid, email, full_name, role, tenant_type, clinic_id, tpa_id in demo_users:
        conn.execute(
            "INSERT OR REPLACE INTO users (id, email, password_hash, full_name, role, tenant_type, clinic_id, tpa_id, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (uid, email, pwd_hash, full_name, role, tenant_type, clinic_id, tpa_id),
        )

def _ensure_migration_table(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, "
        "name TEXT NOT NULL, "
        "applied_at TEXT DEFAULT (datetime('now')))"
    )


def _migration_1_claim_enrichment(conn: sqlite3.Connection):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(claims)").fetchall()}
    migrations = {
        "parsed_evidence": "TEXT",
        "cross_ref_result": "TEXT",
        "evidence_doc_type": "TEXT",
        "evidence_quality": "TEXT",
        "processing_lock": "INTEGER DEFAULT 0",
    }
    for col, dtype in migrations.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE claims ADD COLUMN {col} {dtype}")


def _migration_2_decision_versioning(conn: sqlite3.Connection):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(decisions)").fetchall()}
    if "run_id" not in existing:
        conn.execute("ALTER TABLE decisions ADD COLUMN run_id TEXT")
    if "is_final" not in existing:
        conn.execute("ALTER TABLE decisions ADD COLUMN is_final INTEGER DEFAULT 1")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_claim_run "
        "ON decisions (claim_id, run_id)"
    )


def _migration_3_eligibility_consumptions(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS eligibility_consumptions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "claim_id INTEGER UNIQUE,"
        "member_id TEXT,"
        "covered_amount_myr REAL DEFAULT 0,"
        "created_at TEXT DEFAULT (datetime('now')))"
    )

def _migration_4_pdpa_audit_fields(conn: sqlite3.Connection):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    cols = {
        "data_classification": "TEXT DEFAULT 'SYNTHETIC_PDPA_LOW'",
        "retention_period": "TEXT DEFAULT '7Y'",
        "data_minimization_applied": "INTEGER DEFAULT 1",
        "consent_basis": "TEXT DEFAULT 'CONTRACTUAL_NECESSITY'",
        "cross_border_transfer": "TEXT DEFAULT 'AP-SOUTHEAST-1'",
    }
    for col, ddl in cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} {ddl}")

def _migration_5_hackathon_mvp(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        tenant_type TEXT NOT NULL,
        clinic_id TEXT,
        tpa_id TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS clinics (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        moh_reg_number TEXT UNIQUE NOT NULL,
        panel_tpa_ids TEXT DEFAULT '[]',
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS tpas (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        license_number TEXT UNIQUE NOT NULL,
        contact_email TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL,
        revoked INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS action_notes (
        id TEXT PRIMARY KEY,
        claim_id INTEGER,
        user_id TEXT,
        action_type TEXT,
        note_text TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS token_usage (
        id TEXT PRIMARY KEY,
        claim_id INTEGER,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        total_tokens INTEGER,
        cost_myr REAL
    );
    """)
    existing_audit = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    if "user_id" not in existing_audit:
        conn.execute("ALTER TABLE audit_log ADD COLUMN user_id TEXT")
    if "target_id" not in existing_audit:
        conn.execute("ALTER TABLE audit_log ADD COLUMN target_id TEXT")
        
    existing_claims = {row[1] for row in conn.execute("PRAGMA table_info(claims)").fetchall()}
    if "tpa_id" not in existing_claims:
        conn.execute("ALTER TABLE claims ADD COLUMN tpa_id TEXT")
    if "diagnosis_codes" not in existing_claims:
        conn.execute("ALTER TABLE claims ADD COLUMN diagnosis_codes TEXT")
    if "line_items" not in existing_claims:
        conn.execute("ALTER TABLE claims ADD COLUMN line_items TEXT")


def _migration_6_mc_tracking_and_risk(conn: sqlite3.Connection):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(claims)").fetchall()}
    migrations = {
        "is_mc_issued": "INTEGER DEFAULT 0",
        "mc_days": "INTEGER DEFAULT 0",
        "patient_mc_risk_score": "REAL DEFAULT 0.0",
        "clinic_mc_risk_score": "REAL DEFAULT 0.0",
    }
    for col, dtype in migrations.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE claims ADD COLUMN {col} {dtype}")


def _migration_7_uploaded_assets(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS uploaded_assets ("
        "id TEXT PRIMARY KEY,"
        "filename TEXT,"
        "content_type TEXT,"
        "content_base64 TEXT NOT NULL,"
        "uploaded_by TEXT,"
        "created_at TEXT DEFAULT (datetime('now')))"
    )

MIGRATIONS = [
    (1, "claim_enrichment", _migration_1_claim_enrichment),
    (2, "decision_versioning", _migration_2_decision_versioning),
    (3, "eligibility_consumptions", _migration_3_eligibility_consumptions),
    (4, "pdpa_audit_fields", _migration_4_pdpa_audit_fields),
    (5, "hackathon_mvp", _migration_5_hackathon_mvp),
    (6, "mc_tracking_and_risk", _migration_6_mc_tracking_and_risk),
    (7, "uploaded_assets", _migration_7_uploaded_assets),
]


def _migrate_schema(conn: sqlite3.Connection):
    _ensure_migration_table(conn)
    applied = {
        row["version"]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for version, name, fn in MIGRATIONS:
        if version in applied:
            continue
        logger.info(f"Applying migration {version}: {name}")
        fn(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (version, name),
        )
        conn.commit()

def get_db() -> sqlite3.Connection:
    global _SCHEMA_INITIALIZED, DB_PATH
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    if not _SCHEMA_INITIALIZED:
        try:
            conn.executescript(SCHEMA)
            _migrate_schema(conn)
            _ensure_demo_users(conn)
            conn.commit()
            _SCHEMA_INITIALIZED = True
        except sqlite3.OperationalError as e:
            if "readonly" not in str(e).lower():
                raise
            # Fallback for serverless envs where configured DB_PATH points to read-only FS.
            conn.close()
            DB_PATH = "/tmp/claimiq.db"
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            conn = sqlite3.connect(DB_PATH, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA)
            _migrate_schema(conn)
            _ensure_demo_users(conn)
            conn.commit()
            _SCHEMA_INITIALIZED = True
    return conn

def acquire_processing_lock(claim_id: int) -> bool:
    db = get_db()
    cur = db.execute(
        "UPDATE claims SET processing_lock=1 "
        "WHERE id=? AND COALESCE(processing_lock, 0)=0",
        (claim_id,),
    )
    db.commit()
    db.close()
    return cur.rowcount == 1

def release_processing_lock(claim_id: int):
    db = get_db()
    db.execute("UPDATE claims SET processing_lock=0 WHERE id=?", (claim_id,))
    db.commit()
    db.close()


def log_audit(db: sqlite3.Connection, claim_id: int = None, action: str = "ACTION", from_status: str = None,
              to_status: str = None, details: str = None, actor: str = "SYSTEM",
              data_classification: str = "SYNTHETIC_PDPA_LOW",
              retention_period: str = "7Y",
              data_minimization_applied: int = 1,
              consent_basis: str = "CONTRACTUAL_NECESSITY",
              cross_border_transfer: str = "AP-SOUTHEAST-1",
              user_id: str = None, target_id: str = None):
    db.execute(
        "INSERT INTO audit_log (claim_id, actor, action, from_status, to_status, details, "
        "data_classification, retention_period, data_minimization_applied, consent_basis, cross_border_transfer, user_id, target_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (claim_id, actor, action, from_status, to_status, details, data_classification,
         retention_period, data_minimization_applied, consent_basis, cross_border_transfer, user_id, target_id),
    )

def _tenant_filter(user: dict) -> tuple[str, list]:
    if not user or user.get("role") == "SYSTEM_ADMIN":
        return "", []
    if user.get("tenant_type") == "CLINIC":
        return "clinic_id = ?", [user.get("clinic_id")]
    # TPA users (TPA_PROCESSOR, TPA_FRAUD_ANALYST) see ALL claims — the TPA
    # is the adjudicating body for all panel clinics.  tpa_id is not
    # consistently populated on claims, so we do not filter here.
    if user.get("tenant_type") == "TPA":
        return "", []
    return "1=0", []


def insert_claim(raw_text: str, extracted: Optional[dict] = None) -> int:
    db = get_db()
    ext = json.dumps(extracted) if extracted else None
    cur = db.execute(
        "INSERT INTO claims (raw_text, extracted_data, patient_name, patient_ic, patient_age, "
        "patient_gender, clinic_name, clinic_id, diagnosis, icd10_code, visit_date, "
        "total_amount_myr, consultation_fee_myr, medication_fee_myr, procedure_fee_myr, "
        "is_mc_issued, mc_days, status, lifecycle_stage) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            raw_text, ext,
            extracted.get("patient_name") if extracted else None,
            extracted.get("patient_ic") if extracted else None,
            extracted.get("patient_age") if extracted else None,
            extracted.get("patient_gender") if extracted else None,
            extracted.get("clinic_name") if extracted else None,
            extracted.get("clinic_id") if extracted else None,
            extracted.get("diagnosis") if extracted else None,
            extracted.get("icd10_code") if extracted else None,
            extracted.get("visit_date") if extracted else None,
            extracted.get("total_amount_myr") if extracted else None,
            extracted.get("consultation_fee_myr") if extracted else None,
            extracted.get("medication_fee_myr") if extracted else None,
            extracted.get("procedure_fee_myr") if extracted else None,
            extracted.get("is_mc_issued", 0) if extracted else 0,
            extracted.get("mc_days", 0) if extracted else 0,
            "INTAKE", "INTAKE",
        ),
    )
    db.commit()
    claim_id = cur.lastrowid
    log_audit(db, claim_id, "CLAIM_RECEIVED", to_status="INTAKE")
    db.commit()
    db.close()
    return claim_id


def update_claim(claim_id: int, **kwargs):
    db = get_db()
    old = db.execute("SELECT status FROM claims WHERE id=?", (claim_id,)).fetchone()
    old_status = old["status"] if old else None
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [datetime.utcnow().isoformat(), claim_id]
    db.execute(f"UPDATE claims SET {sets}, updated_at=? WHERE id=?", vals)
    new_status = kwargs.get("status", old_status)
    if new_status != old_status:
        log_audit(db, claim_id, "STATUS_CHANGED", from_status=old_status, to_status=new_status)
    db.commit()
    db.close()


def get_claim(claim_id: int) -> Optional[dict]:
    db = get_db()
    row = db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def list_claims(limit: int = 100, status: Optional[str] = None, clinic: Optional[str] = None) -> list:
    db = get_db()
    conditions, params = [], []
    if status:
        conditions.append("status=?"); params.append(status)
    if clinic:
        conditions.append("clinic_name LIKE ?"); params.append(f"%{clinic}%")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    rows = db.execute(
        f"SELECT * FROM claims {where} ORDER BY created_at DESC LIMIT ?", params + [limit]
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_full_claim(claim_id: int) -> Optional[dict]:
    db = get_db()
    claim = db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    if not claim:
        db.close()
        return None
    result = dict(claim)
    dec = db.execute("SELECT * FROM decisions WHERE claim_id=? ORDER BY created_at DESC LIMIT 1", (claim_id,)).fetchone()
    result["decision"] = dict(dec) if dec else None
    fraud = db.execute("SELECT * FROM fraud_scores WHERE claim_id=? ORDER BY created_at DESC LIMIT 1", (claim_id,)).fetchone()
    result["fraud"] = dict(fraud) if fraud else None
    adv = db.execute("SELECT * FROM advisories WHERE claim_id=? ORDER BY created_at DESC LIMIT 1", (claim_id,)).fetchone()
    result["advisory"] = dict(adv) if adv else None
    eob = db.execute("SELECT * FROM eobs WHERE claim_id=? ORDER BY generated_at DESC LIMIT 1", (claim_id,)).fetchone()
    result["eob"] = dict(eob) if eob else None
    appeals = db.execute("SELECT * FROM appeals WHERE claim_id=? ORDER BY submitted_at DESC", (claim_id,)).fetchall()
    result["appeals"] = [dict(a) for a in appeals]
    audit = db.execute("SELECT * FROM audit_log WHERE claim_id=? ORDER BY created_at ASC", (claim_id,)).fetchall()
    result["audit_trail"] = [dict(a) for a in audit]
    db.close()
    return result


def insert_decision(claim_id: int, result: dict, run_id: Optional[str] = None, is_final: int = 1) -> int:
    db = get_db()
    run_id = run_id or f"legacy-{claim_id}"
    
    # Calculate input hash for audit trace
    import hashlib
    input_str = json.dumps(result.get("full_result", result), sort_keys=True)
    input_hash = hashlib.sha256(input_str.encode()).hexdigest()
    
    existing = db.execute(
        "SELECT id FROM decisions WHERE claim_id=? AND run_id=?",
        (claim_id, run_id),
    ).fetchone()

    payload = (
        result.get("decision"), result.get("confidence"),
        result.get("reasoning"), json.dumps(result.get("policy_references", [])),
        result.get("amount_approved_myr", 0), result.get("amount_denied_myr", 0),
        result.get("patient_responsibility_myr", 0),
        result.get("denial_reason_code"), result.get("denial_reason_description"),
        json.dumps(result.get("conditions", [])), result.get("appeal_recommendation"),
        json.dumps(result), result.get("is_auto_adjudicated", 1), is_final
    )

    if existing:
        db.execute(
            "UPDATE decisions SET decision=?, confidence=?, reasoning=?, policy_references=?, "
            "amount_approved_myr=?, amount_denied_myr=?, patient_responsibility_myr=?, "
            "denial_reason_code=?, denial_reason_description=?, conditions=?, appeal_recommendation=?, "
            "full_result=?, is_auto_adjudicated=?, is_final=?, created_at=datetime('now') "
            "WHERE id=?",
            payload + (existing["id"],),
        )
        cid = existing["id"]
    else:
        cur = db.execute(
        "INSERT INTO decisions (claim_id, run_id, decision, confidence, reasoning, policy_references, "
        "amount_approved_myr, amount_denied_myr, patient_responsibility_myr, "
        "denial_reason_code, denial_reason_description, conditions, appeal_recommendation, "
        "full_result, is_auto_adjudicated, is_final) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            claim_id, run_id, *payload,
        ),
    )
        cid = cur.lastrowid
    db.commit()
    
    # Log immutable decision trace
    trace_details = json.dumps({
        "input_hash": input_hash,
        "model": result.get("model_version", "GLM-v2"),
        "override_reason": result.get("reasoning"),
        "confidence": result.get("confidence")
    })
    log_audit(db, claim_id, "DECISION_RECORDED", details=trace_details, actor="SYSTEM_ADJUDICATOR")
    db.commit()
    
    db.close()
    return cid


def insert_fraud_score(claim_id: int, result: dict) -> int:
    db = get_db()
    # Enforce exactly one fraud row per claim
    db.execute("DELETE FROM fraud_scores WHERE claim_id=?", (claim_id,))
    cur = db.execute(
        "INSERT INTO fraud_scores (claim_id, risk_score, risk_level, flags, recommendation, full_result) "
        "VALUES (?,?,?,?,?,?)",
        (claim_id, result.get("fraud_risk_score"), result.get("risk_level"),
         json.dumps(result.get("flags", [])), result.get("recommendation"), json.dumps(result)),
    )
    db.commit()
    cid = cur.lastrowid
    db.close()
    return cid


def insert_advisory(claim_id: int, result: dict) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO advisories (claim_id, summary, summary_bm, action_items, full_result) "
        "VALUES (?,?,?,?,?)",
        (claim_id, result.get("summary"), result.get("summary_bm"),
         json.dumps(result.get("action_items", [])), json.dumps(result)),
    )
    db.commit()
    cid = cur.lastrowid
    db.close()
    return cid


def insert_eob(claim_id: int, result: dict) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO eobs (claim_id, billed_amount_myr, covered_amount_myr, "
        "patient_responsibility_myr, denial_code, denial_description, eob_text, eob_text_bm) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (claim_id, result.get("billed_amount_myr"), result.get("covered_amount_myr"),
         result.get("patient_responsibility_myr"), result.get("denial_code"),
         result.get("denial_description"), result.get("eob_text"), result.get("eob_text_bm")),
    )
    db.commit()
    cid = cur.lastrowid
    db.close()
    return cid


def insert_appeal(claim_id: int, reason: str, evidence: str, rebuttal: str, rebuttal_bm: str) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO appeals (claim_id, appeal_reason, supporting_evidence, rebuttal_text, rebuttal_bm) "
        "VALUES (?,?,?,?,?)",
        (claim_id, reason, evidence, rebuttal, rebuttal_bm),
    )
    cid = cur.lastrowid
    db.commit()
    db.close()
    update_claim(claim_id, status="APPEALING")
    return cid


def get_member_by_ic(ic_number: str) -> Optional[dict]:
    db = get_db()
    row = db.execute("SELECT * FROM members WHERE ic_number=?", (ic_number,)).fetchone()
    db.close()
    return dict(row) if row else None


def get_clinic_stats(clinic_name: str) -> dict:
    db = get_db()
    stats = db.execute(
        "SELECT COUNT(id) as claims_total, "
        "SUM(CASE WHEN status='APPROVED' THEN 1 ELSE 0 END) as claims_approved, "
        "SUM(CASE WHEN status='DENIED' THEN 1 ELSE 0 END) as claims_denied, "
        "SUM(CASE WHEN status='REFERRED' THEN 1 ELSE 0 END) as claims_referred, "
        "SUM(CASE WHEN fraud_flagged=1 THEN 1 ELSE 0 END) as fraud_flags, "
        "SUM(total_amount_myr) as total_billed_myr "
        "FROM claims WHERE clinic_name LIKE ?", (f"%{clinic_name}%",)
    ).fetchone()
    db.close()
    
    r = dict(stats)
    # Reconcile counts
    if r.get("claims_total") and (r.get("claims_approved", 0) + r.get("claims_denied", 0) + r.get("claims_referred", 0) != r["claims_total"]):
        logger.warning(f"Reconciliation error for {clinic_name}: sums do not match totals.")
        
    return r


def seed_members(members: list):
    db = get_db()
    for m in members:
        db.execute(
            "INSERT OR REPLACE INTO members (member_id, ic_number, name, plan_id, benefit_tier, "
            "coverage_start_date, coverage_end_date, annual_deductible_myr, copay_myr, "
            "max_per_visit_myr, annual_outpatient_limit_myr) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (m["member_id"], m["ic_number"], m["name"], m.get("plan_id", "PMC-STANDARD"),
             m.get("benefit_tier", "STANDARD"), m.get("coverage_start_date", "2024-01-01"),
             m.get("coverage_end_date", "2026-12-31"), m.get("deductible", 0),
             m.get("copay", 10), m.get("max_per_visit", 200), m.get("outpatient_limit", 1000)),
        )
    db.commit()
    db.close()


def has_members_seeded() -> bool:
    db = get_db()
    count = db.execute("SELECT COUNT(*) as c FROM members").fetchone()["c"]
    db.close()
    return count > 0


def consume_member_outpatient_limit(
    claim_id: int,
    member_id: str,
    ic_number: str,
    covered_amount_myr: float,
) -> bool:
    if covered_amount_myr <= 0:
        return False
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        if claim_id:
            seen = db.execute(
                "SELECT 1 FROM eligibility_consumptions WHERE claim_id=?",
                (claim_id,),
            ).fetchone()
            if seen:
                db.rollback()
                return False
        db.execute(
            "UPDATE members SET outpatient_used_myr=COALESCE(outpatient_used_myr,0)+? "
            "WHERE ic_number=?",
            (covered_amount_myr, ic_number),
        )
        if claim_id:
            db.execute(
                "INSERT INTO eligibility_consumptions (claim_id, member_id, covered_amount_myr) "
                "VALUES (?, ?, ?)",
                (claim_id, member_id, covered_amount_myr),
            )
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_analytics_summary() -> dict:
    db = get_db()
    total = db.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    by_status = {}
    for row in db.execute("SELECT status, COUNT(*) as c FROM claims GROUP BY status"):
        by_status[row["status"]] = row["c"]
    avg_amount = db.execute("SELECT AVG(total_amount_myr) as a FROM claims WHERE total_amount_myr IS NOT NULL").fetchone()["a"]
    approved_amt = db.execute(
        "WITH latest AS ("
        "SELECT d.* FROM decisions d "
        "JOIN (SELECT claim_id, MAX(created_at) max_created FROM decisions GROUP BY claim_id) x "
        "ON d.claim_id=x.claim_id AND d.created_at=x.max_created) "
        "SELECT SUM(amount_approved_myr) as a FROM latest"
    ).fetchone()["a"]
    denied_amt = db.execute(
        "WITH latest AS ("
        "SELECT d.* FROM decisions d "
        "JOIN (SELECT claim_id, MAX(created_at) max_created FROM decisions GROUP BY claim_id) x "
        "ON d.claim_id=x.claim_id AND d.created_at=x.max_created) "
        "SELECT SUM(amount_denied_myr) as a FROM latest"
    ).fetchone()["a"]
    fraud_counts = {}
    for row in db.execute("SELECT risk_level, COUNT(*) as c FROM fraud_scores GROUP BY risk_level"):
        fraud_counts[row["risk_level"]] = row["c"]
    # KPI calculations
    approved = by_status.get("APPROVED", 0) + by_status.get("APPEAL_APPROVED", 0)
    denied = by_status.get("DENIED", 0)
    clean_claim_rate = round((approved / total * 100), 1) if total > 0 else 0
    denial_rate = round((denied / total * 100), 1) if total > 0 else 0
    auto_adj = db.execute(
        "WITH latest AS ("
        "SELECT d.* FROM decisions d "
        "JOIN (SELECT claim_id, MAX(created_at) max_created FROM decisions GROUP BY claim_id) x "
        "ON d.claim_id=x.claim_id AND d.created_at=x.max_created) "
        "SELECT COUNT(*) as c FROM latest WHERE is_auto_adjudicated=1"
    ).fetchone()["c"]
    total_adj = db.execute(
        "SELECT COUNT(DISTINCT claim_id) as c FROM decisions"
    ).fetchone()["c"]
    auto_adj_rate = round((auto_adj / total_adj * 100), 1) if total_adj > 0 else 0
    # Appeals
    total_appeals = db.execute("SELECT COUNT(*) as c FROM appeals").fetchone()["c"]
    won_appeals = db.execute("SELECT COUNT(*) as c FROM appeals WHERE appeal_status='APPROVED'").fetchone()["c"]
    appeal_success_rate = round((won_appeals / total_appeals * 100), 1) if total_appeals > 0 else 0
    # Avg AR days (time from filing to payment)
    avg_ar = db.execute("SELECT AVG(ar_days) as a FROM claims WHERE ar_days IS NOT NULL").fetchone()["a"]
    finalized_states = {"APPROVED", "DENIED", "REFERRED", "APPEAL_APPROVED", "APPEAL_DENIED", "PAID", "CLOSED"}
    finalized_total = sum(v for k, v in by_status.items() if k in finalized_states)
    reconciled = finalized_total <= total
    db.close()
    return {
        "total_claims": total,
        "by_status": by_status,
        "avg_claim_amount_myr": round(avg_amount or 0, 2),
        "total_approved_myr": round(approved_amt or 0, 2),
        "total_denied_myr": round(denied_amt or 0, 2),
        "fraud_by_risk_level": fraud_counts,
        "reconciliation": {
            "total_claims": total,
            "finalized_claims": finalized_total,
            "is_consistent": reconciled,
        },
        "kpis": {
            "clean_claim_rate": clean_claim_rate,
            "denial_rate": denial_rate,
            "auto_adjudication_rate": auto_adj_rate,
            "appeal_success_rate": appeal_success_rate,
            "avg_ar_days": round(avg_ar or 0, 1),
        },
    }


def get_clinic_analytics() -> list:
    db = get_db()
    rows = db.execute("""
        WITH latest_decisions AS (
            SELECT d.*
            FROM decisions d
            JOIN (
                SELECT claim_id, MAX(created_at) AS max_created
                FROM decisions
                GROUP BY claim_id
            ) x ON d.claim_id = x.claim_id AND d.created_at = x.max_created
        )
        SELECT c.clinic_name,
               COUNT(*) as total_claims,
               AVG(c.total_amount_myr) as avg_amount,
               SUM(CASE WHEN c.status='APPROVED' THEN 1 ELSE 0 END) as approved,
               SUM(CASE WHEN c.status='DENIED' THEN 1 ELSE 0 END) as denied,
               SUM(CASE WHEN c.fraud_flagged=1 THEN 1 ELSE 0 END) as fraud_flagged,
               AVG(CASE WHEN d.amount_approved_myr IS NOT NULL THEN d.amount_approved_myr END) as avg_approved
        FROM claims c
        LEFT JOIN latest_decisions d ON d.claim_id = c.id
        WHERE c.clinic_name IS NOT NULL
        GROUP BY c.clinic_name
        ORDER BY total_claims DESC
    """).fetchall()
    db.close()
    result = []
    for r in rows:
        r = dict(r)
        r["denial_rate"] = round(r["denied"] / r["total_claims"] * 100, 1) if r["total_claims"] > 0 else 0
        result.append(r)
    return result


def get_denial_breakdown() -> list:
    db = get_db()
    rows = db.execute("""
        WITH latest_decisions AS (
            SELECT d.*
            FROM decisions d
            JOIN (
                SELECT claim_id, MAX(created_at) AS max_created
                FROM decisions
                GROUP BY claim_id
            ) x ON d.claim_id = x.claim_id AND d.created_at = x.max_created
        )
        SELECT denial_reason_code, denial_reason_description, COUNT(*) as count
        FROM latest_decisions
        WHERE decision='DENIED' AND denial_reason_code IS NOT NULL
        GROUP BY denial_reason_code
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


def save_uploaded_asset(asset_id: str, filename: str, content_type: str, content_base64: str, uploaded_by: Optional[str]) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO uploaded_assets (id, filename, content_type, content_base64, uploaded_by) VALUES (?, ?, ?, ?, ?)",
        (asset_id, filename, content_type, content_base64, uploaded_by),
    )
    db.commit()
    db.close()


def get_uploaded_asset(asset_id: str) -> Optional[dict]:
    db = get_db()
    row = db.execute(
        "SELECT id, filename, content_type, content_base64, uploaded_by, created_at FROM uploaded_assets WHERE id=?",
        (asset_id,),
    ).fetchone()
    db.close()
    return dict(row) if row else None


if __name__ == "__main__":
    db = get_db()
    print(f"Database v2 initialized at {DB_PATH}")
    db.close()

