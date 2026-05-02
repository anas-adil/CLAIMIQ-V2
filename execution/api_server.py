import sys, os, json, logging, hashlib, threading, base64, uuid
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, constr
from typing import Optional, List
from datetime import datetime, timezone
import bcrypt
import jwt

import database as db
import claims_processor
import glm_client
import mc_analytics
import eligibility_engine
from auth_middleware import require_role, get_current_user, _get_jwt_secret, security
from fastapi.security import HTTPAuthorizationCredentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("claimiq.api")

app = FastAPI(title="ClaimIQ MVP API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Models ---
class LoginRequest(BaseModel):
    email: str
    password: str

class LineItem(BaseModel):
    description: str
    quantity: int
    unit_price: float
    total: float

class ClaimSubmission(BaseModel):
    raw_text: str
    bill_attached: bool
    evidence_attached: bool
    evidence_base64: Optional[str] = None
    invoice_base64: Optional[str] = None
    evidence_upload_id: Optional[str] = None
    invoice_upload_id: Optional[str] = None
    patient_name: constr(min_length=2, max_length=100)
    patient_ic: constr(pattern=r"^\d{6}-\d{2}-\d{4}$")
    clinic_name: str
    visit_date: constr(pattern=r"^\d{4}-\d{2}-\d{2}$")
    total_amount_myr: float

class RAIRequest(BaseModel):
    request_note: str

class RAIResponse(BaseModel):
    response_note: str

class AppealSubmission(BaseModel):
    appeal_reason: str

class ReviewAction(BaseModel):
    action: constr(pattern=r"^(APPROVED|DENIED|APPROVE|DENY)$")
    reason: Optional[str] = ""

class ChatRequest(BaseModel):
    question: str

class CoverageEligibilityRequest(BaseModel):
    ic_number: constr(pattern=r"^\d{6}-\d{2}-\d{4}$")
    visit_date: constr(pattern=r"^\d{4}-\d{2}-\d{2}$")
    total_amount_myr: float = Field(ge=0)

# --- Routes ---

@app.post("/api/auth/login")
async def login(body: LoginRequest):
    conn = db.get_db()
    user = conn.execute("SELECT * FROM users WHERE email=?", (body.email,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(401, "Invalid email or password")
    
    try:
        password_ok = bcrypt.checkpw(body.password.encode(), user["password_hash"].encode())
    except Exception:
        raise HTTPException(401, "Invalid email or password")
    if not password_ok:
        raise HTTPException(401, "Invalid email or password")
        
    payload = {
        "user_id": user["id"],
        "role": user["role"],
        "tenant_type": user["tenant_type"],
        "tenant_id": user["clinic_id"] or user["tpa_id"] or user["id"],
        "clinic_id": user["clinic_id"],
        "tpa_id": user["tpa_id"],
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(datetime.now(timezone.utc).timestamp()) + 8*3600
    }
    secret = _get_jwt_secret()
    token = jwt.encode(payload, secret, algorithm="HS256")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    conn = db.get_db()
    conn.execute(
        "INSERT INTO sessions (id, user_id, token_hash, expires_at) VALUES (?, ?, ?, ?)",
        (os.urandom(16).hex(), user["id"], token_hash, datetime.fromtimestamp(payload["exp"]).isoformat())
    )
    db.log_audit(conn, action="LOGIN", user_id=user["id"])
    conn.commit()
    conn.close()
    
    redirect_map = {
        "CLINIC_USER": "#/portal/clinic",
        "TPA_PROCESSOR": "#/portal/tpa",
        "TPA_FRAUD_ANALYST": "#/portal/tpa",
        "SYSTEM_ADMIN": "#/portal/admin"
    }
    return {
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "redirect": redirect_map.get(user["role"], "#/"),
        "user": {"id": user["id"], "email": user["email"], "role": user["role"], "tenant_type": user["tenant_type"]}
    }

@app.post("/api/auth/logout")
async def logout(
    user: dict = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    conn = db.get_db()
    conn.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (token_hash,))
    db.log_audit(conn, action="LOGOUT", user_id=user["user_id"])
    conn.commit()
    conn.close()
    return {"message": "Logged out"}


@app.post("/api/uploads")
async def upload_supporting_file(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["CLINIC_USER", "SYSTEM_ADMIN"])),
):
    max_bytes = 4 * 1024 * 1024  # Keep comfortably below typical serverless payload ceilings.
    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty")
    if len(content) > max_bytes:
        raise HTTPException(413, f"File too large. Max allowed is {max_bytes // (1024 * 1024)}MB")

    content_type = file.content_type or "application/octet-stream"
    encoded = base64.b64encode(content).decode("utf-8")
    data_url = f"data:{content_type};base64,{encoded}"
    asset_id = uuid.uuid4().hex
    db.save_uploaded_asset(
        asset_id=asset_id,
        filename=file.filename or "upload.bin",
        content_type=content_type,
        content_base64=data_url,
        uploaded_by=user.get("user_id"),
    )
    return {"upload_id": asset_id, "filename": file.filename, "content_type": content_type, "size_bytes": len(content)}

@app.post("/api/claims/submit")
async def submit_claim(body: ClaimSubmission, user: dict = Depends(require_role(["CLINIC_USER", "SYSTEM_ADMIN"]))):
    visit = datetime.strptime(body.visit_date, "%Y-%m-%d").date()
    if visit > datetime.now(timezone.utc).date():
        raise HTTPException(422, "Visit date cannot be in the future")

    # Total amount validation logic is deferred to the scrubber because line items are not parsed yet
        
    evidence_base64 = body.evidence_base64
    if body.evidence_upload_id:
        asset = db.get_uploaded_asset(body.evidence_upload_id)
        if not asset:
            raise HTTPException(400, "Evidence upload not found")
        evidence_base64 = asset.get("content_base64")

    invoice_base64 = body.invoice_base64
    if body.invoice_upload_id:
        asset = db.get_uploaded_asset(body.invoice_upload_id)
        if not asset:
            raise HTTPException(400, "Invoice upload not found")
        invoice_base64 = asset.get("content_base64")

    conn = db.get_db()
    dup = conn.execute(
        "SELECT id FROM claims WHERE clinic_id=? AND patient_ic=? AND visit_date=? AND ABS(total_amount_myr-?) < 0.01 "
        "AND status NOT IN ('ERROR') ORDER BY created_at DESC LIMIT 1",
        (user["clinic_id"], body.patient_ic, body.visit_date, body.total_amount_myr),
    ).fetchone()
    if dup:
        conn.close()
        raise HTTPException(409, f"Potential duplicate claim detected (claim_id={dup['id']})")

    cur = conn.execute(
        "INSERT INTO claims (status, lifecycle_stage, patient_ic, patient_name, visit_date, "
        "clinic_id, clinic_name, raw_text, extracted_data, total_amount_myr) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("SUBMITTED", "SUBMITTED", body.patient_ic, body.patient_name, body.visit_date,
         user["clinic_id"], body.clinic_name, body.raw_text, json.dumps({
             "patient_name": body.patient_name,
             "patient_ic": body.patient_ic,
             "clinic_name": body.clinic_name,
             "visit_date": body.visit_date,
             "total_amount_myr": body.total_amount_myr,
             "_evidence_base64": evidence_base64,
             "_invoice_base64": invoice_base64,
             "_bill_attached": bool(body.bill_attached),
             "_evidence_attached": bool(body.evidence_attached),
         }), body.total_amount_myr)
    )
    claim_id = cur.lastrowid
    db.log_audit(conn, claim_id=claim_id, action="CLAIM_SUBMITTED", user_id=user["user_id"], to_status="SUBMITTED")
    conn.commit()
    conn.close()
    
    # Run the heavy processing pipeline in a background thread so the API
    # returns immediately. The frontend polls /api/claims/{id} to track progress.
    def _bg_process():
        try:
            claims_processor.process_claim(claim_id=claim_id)
        except Exception as e:
            logger.error(f"Background processing failed for claim {claim_id}: {e}")
    
    t = threading.Thread(target=_bg_process, daemon=True)
    t.start()
        
    return {"claim_id": claim_id, "status": "SUBMITTED"}

@app.get("/api/claims/")
async def get_claims_queue(
    limit: int = 100,
    status: Optional[str] = None,
    clinic: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    conn = db.get_db()
    tf_clause, tf_params = db._tenant_filter(user)
    conditions = []
    params: list = []
    if tf_clause:
        conditions.append(tf_clause)
        params.extend(tf_params)
    if status:
        conditions.append("status=?")
        params.append(status)
    if clinic:
        conditions.append("clinic_name LIKE ?")
        params.append(f"%{clinic}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"SELECT c.id, c.patient_name, c.patient_ic, c.visit_date, c.created_at, c.clinic_name, c.clinic_id, "
        f"c.diagnosis, c.icd10_code, c.total_amount_myr, c.status, "
        f"COALESCE(tu.total_tokens, 0) AS ai_total_tokens, COALESCE(tu.total_cost_myr, 0) AS ai_total_cost_myr "
        f"FROM claims c "
        f"LEFT JOIN ("
        f"  SELECT claim_id, SUM(total_tokens) AS total_tokens, SUM(cost_myr) AS total_cost_myr "
        f"  FROM token_usage WHERE claim_id IS NOT NULL GROUP BY claim_id"
        f") tu ON tu.claim_id = c.id "
        f"{where.replace('WHERE ', 'WHERE c.') if where else ''} "
        f"ORDER BY c.created_at DESC LIMIT ?",
        params + [max(1, min(limit, 500))],
    ).fetchall()
    conn.close()
    claims = []
    for r in rows:
        d = dict(r)
        d["claim_id"] = d["id"]
        d["total_amount"] = d.get("total_amount_myr")
        claims.append(d)
    return {"claims": claims}

@app.get("/api/claims/{claim_id}")
async def get_claim_detail(claim_id: int, user: dict = Depends(get_current_user)):
    conn = db.get_db()
    tf_clause, tf_params = db._tenant_filter(user)
    claim = conn.execute(f"SELECT * FROM claims WHERE id=? AND ({tf_clause or '1=1'})", [claim_id] + tf_params).fetchone()
    if not claim:
        conn.close()
        raise HTTPException(404, "Claim not found")
        
    res = dict(claim)
    res["diagnosis_codes"] = json.loads(res.get("diagnosis_codes") or "[]")
    res["line_items"] = json.loads(res.get("line_items") or "[]")
    try:
        res["cross_ref_result"] = json.loads(res.get("cross_ref_result") or "{}")
    except (TypeError, json.JSONDecodeError):
        res["cross_ref_result"] = {}
    
    actions = conn.execute("SELECT * FROM action_notes WHERE claim_id=? ORDER BY created_at ASC", (claim_id,)).fetchall()
    res["action_history"] = [dict(a) for a in actions]

    # --- Helper to safely parse JSON strings from SQLite columns ---
    def _safe_json_parse(value, default=None):
        if value is None or value == "":
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            parsed = json.loads(value)
            return parsed if parsed is not None else default
        except (TypeError, json.JSONDecodeError):
            return default

    decision = conn.execute("SELECT * FROM decisions WHERE claim_id=? ORDER BY id DESC LIMIT 1", (claim_id,)).fetchone()
    if decision:
        dec_dict = dict(decision)
        # Parse JSON string columns
        dec_dict["policy_references"] = _safe_json_parse(dec_dict.get("policy_references"), [])
        dec_dict["conditions"] = _safe_json_parse(dec_dict.get("conditions"), [])
        # Merge full_result keys into the top-level decision dict so the frontend
        # can access fields like _ai_decision, reasoning_citations, denial_prediction,
        # disposition_class, rule_hits, etc. without digging into full_result.
        full_result = _safe_json_parse(dec_dict.get("full_result"), {})
        if isinstance(full_result, dict):
            for key, value in full_result.items():
                if key not in dec_dict or dec_dict[key] is None:
                    dec_dict[key] = value
        # Remove the raw full_result string to avoid sending duplicate data
        dec_dict.pop("full_result", None)
        res["decision"] = dec_dict
    else:
        res["decision"] = None

    fraud = conn.execute("SELECT * FROM fraud_scores WHERE claim_id=? ORDER BY id DESC LIMIT 1", (claim_id,)).fetchone()
    if fraud:
        fraud_dict = dict(fraud)
        # Parse flags from JSON string to array
        fraud_dict["flags"] = _safe_json_parse(fraud_dict.get("flags"), [])
        # Merge full_result keys (e.g. graph_signal, fraud_risk_score alias)
        fraud_full = _safe_json_parse(fraud_dict.get("full_result"), {})
        if isinstance(fraud_full, dict):
            for key, value in fraud_full.items():
                if key not in fraud_dict or fraud_dict[key] is None:
                    fraud_dict[key] = value
        fraud_dict.pop("full_result", None)
        res["fraud"] = fraud_dict
    else:
        res["fraud"] = None

    token_usage = conn.execute(
        "SELECT COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens, "
        "COALESCE(SUM(completion_tokens), 0) AS completion_tokens, "
        "COALESCE(SUM(total_tokens), 0) AS total_tokens, "
        "COALESCE(SUM(cost_myr), 0) AS total_cost_myr "
        "FROM token_usage WHERE claim_id=?",
        (claim_id,),
    ).fetchone()
    res["ai_usage"] = dict(token_usage) if token_usage else {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "total_cost_myr": 0.0,
    }

    # advisory — needed by the GP Advisory card in the claim modal
    advisory = conn.execute("SELECT * FROM advisories WHERE claim_id=? ORDER BY id DESC LIMIT 1", (claim_id,)).fetchone()
    if advisory:
        adv_dict = dict(advisory)
        adv_dict["action_items"] = _safe_json_parse(adv_dict.get("action_items"), [])
        adv_full = _safe_json_parse(adv_dict.get("full_result"), {})
        if isinstance(adv_full, dict):
            for key, value in adv_full.items():
                if key not in adv_dict or adv_dict[key] is None:
                    adv_dict[key] = value
        adv_dict.pop("full_result", None)
        res["advisory"] = adv_dict
    else:
        res["advisory"] = None

    # eob — needed by the EOB card in the claim modal
    eob = conn.execute("SELECT * FROM eobs WHERE claim_id=? ORDER BY generated_at DESC LIMIT 1", (claim_id,)).fetchone()
    res["eob"] = dict(eob) if eob else None

    # audit_trail — needed by the Audit Timeline section in the claim modal
    audit = conn.execute("SELECT * FROM audit_log WHERE claim_id=? ORDER BY created_at ASC", (claim_id,)).fetchall()
    res["audit_trail"] = [dict(a) for a in audit]

    conn.close()
    return res

@app.post("/api/claims/{claim_id}/rai")
async def raise_rai(claim_id: int, body: RAIRequest, user: dict = Depends(require_role(["TPA_PROCESSOR"]))):
    conn = db.get_db()
    conn.execute("INSERT INTO action_notes (id, claim_id, user_id, action_type, note_text) VALUES (?, ?, ?, ?, ?)",
                 (os.urandom(16).hex(), claim_id, user["user_id"], "RAI_REQUEST", body.request_note))
    conn.execute("UPDATE claims SET status='PENDING_RAI' WHERE id=?", (claim_id,))
    db.log_audit(conn, claim_id=claim_id, action="RAI_REQUESTED", user_id=user["user_id"], to_status="PENDING_RAI")
    conn.commit()
    conn.close()
    return {"status": "PENDING_RAI"}

@app.post("/api/claims/{claim_id}/rai-response")
async def respond_rai(claim_id: int, body: RAIResponse, user: dict = Depends(require_role(["CLINIC_USER"]))):
    conn = db.get_db()
    conn.execute("INSERT INTO action_notes (id, claim_id, user_id, action_type, note_text) VALUES (?, ?, ?, ?, ?)",
                 (os.urandom(16).hex(), claim_id, user["user_id"], "RAI_RESPONSE", body.response_note))
    conn.execute("UPDATE claims SET status='UNDER_REVIEW' WHERE id=?", (claim_id,))
    db.log_audit(conn, claim_id=claim_id, action="RAI_RESPONDED", user_id=user["user_id"], to_status="UNDER_REVIEW")
    conn.commit()
    conn.close()
    return {"status": "UNDER_REVIEW"}

@app.post("/api/claims/{claim_id}/appeal")
async def appeal_claim(claim_id: int, body: AppealSubmission, user: dict = Depends(require_role(["CLINIC_USER"]))):
    conn = db.get_db()
    tf_clause, tf_params = db._tenant_filter(user)
    claim = conn.execute(
        f"SELECT id, status FROM claims WHERE id=? AND ({tf_clause or '1=1'})",
        [claim_id] + tf_params,
    ).fetchone()
    if not claim:
        conn.close()
        raise HTTPException(404, "Claim not found")
    allowed = {"DENIED", "REFERRED", "PENDING_DENIAL", "PENDING_APPROVAL"}
    if claim["status"] not in allowed:
        conn.close()
        raise HTTPException(409, "Claim is not in an appealable status")

    conn.execute("INSERT INTO action_notes (id, claim_id, user_id, action_type, note_text) VALUES (?, ?, ?, ?, ?)",
                 (os.urandom(16).hex(), claim_id, user["user_id"], "APPEAL", body.appeal_reason))
    conn.execute("UPDATE claims SET status='UNDER_REVIEW' WHERE id=?", (claim_id,))
    db.log_audit(conn, claim_id=claim_id, action="CLAIM_APPEALED", user_id=user["user_id"], to_status="UNDER_REVIEW")
    conn.commit()
    conn.close()
    return {"status": "UNDER_REVIEW"}

@app.post("/api/claims/{claim_id}/review")
async def review_claim(claim_id: int, body: ReviewAction, user: dict = Depends(require_role(["TPA_PROCESSOR", "SYSTEM_ADMIN"]))):
    final_action = "APPROVED" if body.action == "APPROVE" else ("DENIED" if body.action == "DENY" else body.action)
    # Verify the claim exists and is in a reviewable state
    claim = db.get_full_claim(claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    conn = db.get_db()
    db.update_claim(claim_id, status=final_action)
    db.log_audit(conn, claim_id=claim_id, action=f"CLAIM_MANUAL_{final_action}", user_id=user["user_id"], to_status=final_action, details=body.reason)
    conn.commit()
    conn.close()
    return {"status": final_action}

@app.post("/api/claims/{claim_id}/chat")
async def chat_with_claim(claim_id: int, body: ChatRequest, user: dict = Depends(get_current_user)):
    conn = db.get_db()
    tf_clause, tf_params = db._tenant_filter(user)
    claim = conn.execute(f"SELECT * FROM claims WHERE id=? AND ({tf_clause or '1=1'})", [claim_id] + tf_params).fetchone()
    if not claim:
        conn.close()
        raise HTTPException(404, "Claim not found")
    
    decision = conn.execute("SELECT * FROM decisions WHERE claim_id=? ORDER BY id DESC LIMIT 1", (claim_id,)).fetchone()
    fraud = conn.execute("SELECT * FROM fraud_scores WHERE claim_id=? ORDER BY id DESC LIMIT 1", (claim_id,)).fetchone()
    conn.close()
    
    claim_dict = dict(claim)

    def _safe_json(value, default):
        if value is None or value == "":
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            parsed = json.loads(value)
            return parsed if parsed is not None else default
        except (TypeError, json.JSONDecodeError):
            return default

    extracted_data = _safe_json(claim_dict.get("extracted_data"), {})
    parsed_evidence = _safe_json(claim_dict.get("parsed_evidence"), [])
    cross_ref_result = _safe_json(claim_dict.get("cross_ref_result"), {})
    diagnosis = claim_dict.get("diagnosis") or extracted_data.get("diagnosis")

    invoice_summary = None
    if isinstance(parsed_evidence, list):
        for ev in parsed_evidence:
            if not isinstance(ev, dict):
                continue
            triage = ev.get("triage") or {}
            if (triage.get("doc_type") or "").upper() != "INVOICE":
                continue
            parsed_inv = ev.get("parsed_evidence") or {}
            if not isinstance(parsed_inv, dict):
                continue
            item_keys = ["line_items", "items", "invoice_items"]
            line_items = []
            for k in item_keys:
                if isinstance(parsed_inv.get(k), list):
                    line_items = parsed_inv.get(k)
                    break
            inv_total = (
                parsed_inv.get("total_amount")
                or parsed_inv.get("invoice_total")
                or parsed_inv.get("total")
            )
            summary_parts = []
            if inv_total not in (None, ""):
                summary_parts.append(f"total billed RM {inv_total}")
            if line_items:
                summary_parts.append(f"{len(line_items)} line item(s)")
            invoice_summary = "; ".join(summary_parts) if summary_parts else "invoice was parsed but no totals/line items were confidently extracted"
            break

    context = {
        "claim_id": claim_id,
        "status": claim_dict.get("status"),
        "diagnosis": diagnosis,
        "icd10_code": claim_dict.get("icd10_code") or extracted_data.get("icd10_code") or extracted_data.get("primary_diagnosis_code"),
        "total_amount_myr": claim_dict.get("total_amount_myr"),
        "patient_name": claim_dict.get("patient_name") or extracted_data.get("patient_name"),
        "clinic_name": claim_dict.get("clinic_name") or extracted_data.get("clinic_name"),
        "raw_text": (claim_dict.get("raw_text") or "")[:12000],
        "extracted_data": extracted_data,
        "parsed_evidence": parsed_evidence,
        "cross_reference": cross_ref_result,
        "invoice_summary": invoice_summary,
        "decision": dict(decision) if decision else None,
        "fraud": dict(fraud) if fraud else None,
    }
    
    try:
        answer = glm_client.answer_claim_question(body.question, context)
        return answer
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return {"answer": f"I could not process your question at this time. Error: {str(e)}", "follow_up_questions": []}

@app.get("/api/tpa/claims/queue")
async def tpa_queue(user: dict = Depends(require_role(["TPA_PROCESSOR"]))):
    conn = db.get_db()
    claims = conn.execute("SELECT id as claim_id, patient_name, visit_date, total_amount_myr as total_amount, status FROM claims WHERE status IN ('UNDER_REVIEW', 'SUBMITTED', 'PENDING_RAI')").fetchall()
    conn.close()
    return {"claims": [dict(c) for c in claims]}

@app.get("/api/tpa/fraud/flagged")
async def fraud_queue(user: dict = Depends(require_role(["TPA_FRAUD_ANALYST"]))):
    conn = db.get_db()
    claims = conn.execute("SELECT id as claim_id, patient_name, visit_date, total_amount_myr as total_amount, status FROM claims WHERE status = 'FRAUD_FLAG'").fetchall()
    conn.close()
    return {"claims": [dict(c) for c in claims]}

@app.post("/api/tpa/fraud/{claim_id}/confirm")
async def fraud_confirm(claim_id: int, user: dict = Depends(require_role(["TPA_FRAUD_ANALYST"]))):
    conn = db.get_db()
    conn.execute("UPDATE claims SET status='DENIED' WHERE id=?", (claim_id,))
    db.log_audit(conn, claim_id=claim_id, action="FRAUD_CONFIRMED", user_id=user["user_id"], to_status="DENIED")
    conn.commit()
    conn.close()
    return {"status": "DENIED"}

@app.post("/api/tpa/fraud/{claim_id}/clear")
async def fraud_clear(claim_id: int, user: dict = Depends(require_role(["TPA_FRAUD_ANALYST"]))):
    conn = db.get_db()
    conn.execute("UPDATE claims SET status='UNDER_REVIEW' WHERE id=?", (claim_id,))
    db.log_audit(conn, claim_id=claim_id, action="FRAUD_CLEARED", user_id=user["user_id"], to_status="UNDER_REVIEW")
    conn.commit()
    conn.close()
    return {"status": "UNDER_REVIEW"}

@app.post("/api/demo/seed")
async def demo_seed(user: dict = Depends(require_role(["SYSTEM_ADMIN"]))):
    from generate_synthetic_data import seed_hackathon_demo
    return seed_hackathon_demo()

@app.get("/api/metrics")
async def metrics(user: dict = Depends(get_current_user)):
    usage = glm_client.get_token_metrics()
    summary = db.get_analytics_summary()
    total_claims = summary.get("total_claims") or 0

    conn = db.get_db()
    token_totals = conn.execute(
        "SELECT COALESCE(SUM(total_tokens), 0) AS total_tokens, "
        "COALESCE(SUM(cost_myr), 0) AS total_cost_myr, "
        "COUNT(DISTINCT claim_id) AS claims_with_usage "
        "FROM token_usage WHERE claim_id IS NOT NULL"
    ).fetchone()
    conn.close()

    db_total_tokens = int(token_totals["total_tokens"] or 0)
    db_total_cost_myr = float(token_totals["total_cost_myr"] or 0.0)
    db_claims_with_usage = int(token_totals["claims_with_usage"] or 0)
    live_total_tokens = int(usage.get("total_tokens") or 0)
    live_total_cost_myr = float(usage.get("total_cost_myr") or 0.0)
    live_claims_with_usage = int(usage.get("claims_with_usage") or 0)
    live_calls = int(usage.get("calls") or 0)

    # Prefer live in-memory counters for active runtime telemetry.
    # Fall back to DB totals when the process has no live usage data.
    if live_calls > 0 or live_total_tokens > 0:
        effective_total_tokens = live_total_tokens
        effective_total_cost_myr = live_total_cost_myr if live_total_cost_myr > 0 else db_total_cost_myr
        claims_with_usage = live_claims_with_usage if live_claims_with_usage > 0 else db_claims_with_usage
    else:
        effective_total_tokens = db_total_tokens
        effective_total_cost_myr = db_total_cost_myr
        claims_with_usage = db_claims_with_usage

    usage["total_tokens"] = effective_total_tokens
    usage["total_cost_myr"] = effective_total_cost_myr
    usage["claims_with_usage"] = claims_with_usage
    usage["lifetime_total_tokens"] = db_total_tokens
    usage["avg_tokens_per_claim"] = round(effective_total_tokens / total_claims, 2) if total_claims else 0.0
    usage["avg_cost_per_claim_myr"] = round(effective_total_cost_myr / total_claims, 8) if total_claims else 0.0
    usage["avg_cost_per_processed_claim_myr"] = round(effective_total_cost_myr / claims_with_usage, 8) if claims_with_usage else 0.0
    return usage

@app.get("/api/analytics/summary")
async def analytics_summary(user: dict = Depends(get_current_user)):
    return db.get_analytics_summary()

@app.get("/api/analytics/denials")
async def analytics_denials(user: dict = Depends(get_current_user)):
    return {"breakdown": db.get_denial_breakdown()}

@app.get("/api/analytics/clinics")
async def analytics_clinics(user: dict = Depends(require_role(["TPA_PROCESSOR", "TPA_FRAUD_ANALYST", "SYSTEM_ADMIN"]))):
    return {"clinics": db.get_clinic_analytics()}

@app.get("/api/analytics/mc-patterns")
async def analytics_mc_patterns(user: dict = Depends(require_role(["TPA_PROCESSOR", "TPA_FRAUD_ANALYST", "SYSTEM_ADMIN"]))):
    return mc_analytics.get_mc_behavior_patterns()

@app.get("/api/analytics/fraud-heatmap")
async def analytics_fraud_heatmap(user: dict = Depends(get_current_user)):
    conn = db.get_db()
    tf_clause, tf_params = db._tenant_filter(user)
    where = f"WHERE {tf_clause}" if tf_clause else ""
    rows = conn.execute(
        "SELECT c.id AS claim_id, c.clinic_name, c.diagnosis, c.total_amount_myr, "
        "f.risk_score, f.risk_level "
        "FROM fraud_scores f JOIN claims c ON c.id=f.claim_id "
        f"{where} ORDER BY f.id DESC",
        tf_params,
    ).fetchall()
    conn.close()
    return {"heatmap_data": [dict(r) for r in rows]}

@app.get("/api/analytics/weekly-report")
async def analytics_weekly_report(user: dict = Depends(get_current_user)):
    summary = db.get_analytics_summary()
    return glm_client.generate_weekly_report(summary)

@app.post("/api/fhir/coverage-eligibility")
async def fhir_coverage_eligibility(body: CoverageEligibilityRequest, user: dict = Depends(get_current_user)):
    result = eligibility_engine.check_eligibility(body.ic_number, body.visit_date, body.total_amount_myr)
    eligible = bool(result.get("eligible"))
    covered = float(result.get("covered_amount_myr") or 0.0)
    patient_resp = float(result.get("patient_responsibility_myr") or 0.0)
    return {
        "resourceType": "EligibilityResponse",
        "outcome": "complete",
        "insurance": [{
            "inforce": eligible,
            "benefitBalance": [{
                "financial": [
                    {"type": {"text": "covered"}, "allowedMoney": {"value": covered, "currency": "MYR"}},
                    {"type": {"text": "patient_responsibility"}, "allowedMoney": {"value": patient_resp, "currency": "MYR"}},
                ]
            }],
        }],
        "meta": {"generated_at": datetime.now(timezone.utc).isoformat()},
    }

@app.get("/api/claims/{claim_id}/export")
async def export_claim(claim_id: int, user: dict = Depends(get_current_user)):
    claim = db.get_full_claim(claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    tf_clause, tf_params = db._tenant_filter(user)
    if tf_clause:
        conn = db.get_db()
        row = conn.execute(f"SELECT id FROM claims WHERE id=? AND ({tf_clause})", [claim_id] + tf_params).fetchone()
        conn.close()
        if not row:
            raise HTTPException(404, "Claim not found")
    return {"claim_id": claim_id, "claim": claim}

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ClaimIQ MVP"}

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
