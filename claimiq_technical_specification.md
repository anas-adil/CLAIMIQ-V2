# ClaimIQ — EXHAUSTIVE TECHNICAL SPECIFICATION v1.0 (HACKATHON MVP)

**Stack:** FastAPI · SQLite · Vanilla JS/CSS/HTML · FAISS RAG · OpenAI-compatible GLM  
**Focus:** Live Technical Demonstration, Production-Ready Code, Token Efficiency, Integration Security.
**Requirement:** Zero-ambiguity. Every technical decision required for the MVP is stated here.

---

## SECTION A — AUTHENTICATION & SESSION SYSTEM

### A.1 Auth Mechanism: JWT (HS256)

**Signing key:** `JWT_SECRET` env var (minimum 64 characters). Server refuses to start if missing or < 64 chars.
**Token lifetime:** 8 hours. No refresh tokens. Library: `PyJWT`.

**JWT payload fields (exact):**
- `user_id`: string (UUID)
- `role`: string (Enum matching A.2)
- `tenant_type`: string (`CLINIC` | `TPA` | `SYSTEM`)
- `tenant_id`: string (UUID, equals clinic_id or tpa_id. For SYSTEM, equals user_id)
- `clinic_id`: string (UUID) | null
- `tpa_id`: string (UUID) | null
- `iat`: int (Issued-at Unix timestamp)
- `exp`: int (Expiry Unix timestamp)

### A.2 Roles Enum (4 Core Values)

`CLINIC_USER`, `TPA_PROCESSOR`, `TPA_FRAUD_ANALYST`, `SYSTEM_ADMIN`

### A.3 Multi-Tenancy Model

- A user belongs to exactly one tenant. Enforced by DB constraints: exactly one of `clinic_id` or `tpa_id` is non-null, OR role is `SYSTEM_ADMIN` (both null).
- Every DB query appends a `WHERE` clause filtering by the caller's `tenant_id`. No exceptions. Helper function: `_tenant_filter(request.state.user)`.

### A.4 Login & Redirect

**Endpoint:** `POST /api/auth/login`
**Body:** `{ "email": str, "password": str }`
**Response:** `{ "token": "<jwt>", "redirect": "<path>", "user": { "id": str, "email": str, "role": str, "tenant_type": str } }`

**Redirect mapping:**
- `CLINIC_USER` → `#/portal/clinic`
- `TPA_PROCESSOR`, `TPA_FRAUD_ANALYST` → `#/portal/tpa`
- `SYSTEM_ADMIN` → `#/portal/admin`

**Password hashing:** `bcrypt` with cost factor 12.
**Logout:** `POST /api/auth/logout` — sets `sessions.revoked = 1`.

### A.5 DB Tables (Schema)

**Table: `users`**
- `id` TEXT PK UUID
- `email` TEXT UNIQUE NOT NULL
- `password_hash` TEXT NOT NULL
- `full_name` TEXT NOT NULL
- `role` TEXT NOT NULL
- `tenant_type` TEXT NOT NULL
- `clinic_id` TEXT FK → clinics.id (nullable)
- `tpa_id` TEXT FK → tpas.id (nullable)
- `is_active` INTEGER DEFAULT 1
- `created_at` TEXT DEFAULT datetime('now')

**Table: `clinics`**
- `id` TEXT PK UUID
- `name` TEXT NOT NULL
- `moh_reg_number` TEXT UNIQUE NOT NULL
- `panel_tpa_ids` TEXT DEFAULT '[]' (JSON array)
- `is_active` INTEGER DEFAULT 1
- `created_at` TEXT DEFAULT datetime('now')

**Table: `tpas`**
- `id` TEXT PK UUID
- `name` TEXT NOT NULL
- `license_number` TEXT UNIQUE NOT NULL
- `contact_email` TEXT NOT NULL
- `is_active` INTEGER DEFAULT 1
- `created_at` TEXT DEFAULT datetime('now')

**Table: `sessions`**
- `id` TEXT PK UUID
- `user_id` TEXT FK → users.id NOT NULL
- `token_hash` TEXT NOT NULL (SHA256 of JWT string)
- `created_at` TEXT DEFAULT datetime('now')
- `expires_at` TEXT NOT NULL
- `revoked` INTEGER DEFAULT 0

### A.6 API Auth Middleware

**Exempt routes:** `/api/health`, `/api/auth/login`, static files.
**Implementation:** `auth_middleware.py`. Decodes JWT, verifies signature + expiry, queries `sessions` table to ensure `revoked=0`. Injects decoded payload into `request.state.user`. On failure: returns `401`.

**Role decorator pattern:**
```python
def require_role(allowed_roles: list[str]):
    def decorator(func):
        async def wrapper(request, *args, **kwargs):
            if request.state.user["role"] not in allowed_roles:
                raise HTTPException(403, "INSUFFICIENT_ROLE")
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
```

---

## SECTION B — PORTAL ROUTING & UI SPECIFICATIONS

Frontend remains Vanilla JS. Hash-based routing (`window.location.hash`).

### B.1 CLINIC PORTAL (`#/portal/clinic`)
**Allowed Role:** `CLINIC_USER`
**Page Load Call:** `GET /api/claims/?clinic_id={session.clinic_id}`
**Tabs:**
- **Submit Claim:** Form strictly matching Section C.
- **Claims Queue:** Table with columns `claim_id, patient_name, visit_date, total_amount, status`.
- **Claim Detail View:** Displays all submitted data + AI decision summary. If status is `DENIED`, an "Appeal" button appears. If `PENDING_RAI`, a "Respond to Request" form appears.

### B.2 TPA PORTAL (`#/portal/tpa`)
**Allowed Roles:** `TPA_PROCESSOR`, `TPA_FRAUD_ANALYST`

**If TPA_PROCESSOR:**
- **Page Load:** `GET /api/tpa/claims/queue` (Only shows claims where `fraud_score < 0.70`).
- **Claim Detail:** Full clinical data, GLM AI reasoning. Action buttons: "Approve", "Deny", "Raise RAI".

**If TPA_FRAUD_ANALYST:**
- **Page Load:** `GET /api/tpa/fraud/flagged` (Only shows claims where `fraud_score >= 0.70`).
- **Dashboard:** Provider Risk Leaderboard (`GET /api/tpa/fraud/providers`), Heatmap (`GET /api/analytics/fraud-heatmap`), Network Graph (`GET /api/tpa/fraud/network`).
- **Claim Detail Action Buttons:** "Confirm Fraud", "Clear Flag". (Cannot adjudicate / Approve).

### B.3 SYSTEM ADMIN PORTAL (`#/portal/admin`)
**Allowed Role:** `SYSTEM_ADMIN`
- **User Management:** Create clinics, TPAs, and users (`POST /api/admin/users`).
- **Audit Viewer:** `GET /api/admin/audit-log` to render an immutable list of system actions.

---

## SECTION C — CLAIM SUBMISSION FLOW

**Endpoint:** `POST /api/claims/submit`
**Format:** `multipart/form-data`

**Exact Payload Validation:**
| Field | Type | Validation | Required |
|---|---|---|---|
| `patient_ic` | string | Regex `^\d{6}-\d{2}-\d{4}$` | Yes |
| `patient_name` | string | min 2, max 100 chars | Yes |
| `visit_date` | string | YYYY-MM-DD, cannot be future | Yes |
| `clinic_id` | string | Enforced server-side from session | Yes |
| `diagnosis_codes` | string[] | JSON array of ICD-10 strings, min 1 | Yes |
| `line_items` | string | JSON array of `{desc: str, qty: int, price: float, total: float}` | Yes |
| `total_amount` | float | Server must validate it matches sum of line_items totals | Yes |
| `supporting_docs` | File[] | PDF/JPG/PNG. Max 5. Max 5MB each. | No |

**Success Response:** `{"claim_id": "<uuid>", "status": "SUBMITTED"}`

---

## SECTION D — STATE MACHINE (MVP 7 Statuses)

**1. DRAFT**
- **Trigger:** Clinic saves incomplete form.
- **Next:** `SUBMITTED`.

**2. SUBMITTED**
- **Trigger:** Clinic submits valid form.
- **Action:** System executes the AI pipeline (`claims_processor.py`). Transitions claim to `UNDER_REVIEW` (or `FRAUD_FLAG` if score > 0.70).

**3. UNDER_REVIEW**
- **Trigger:** AI evaluation finishes.
- **Display:** "Under Review".
- **Next:** `APPROVED`, `DENIED`, `PENDING_RAI`.
- **Action:** `TPA_PROCESSOR` executes `POST /api/claims/{id}/review` with `{"action": "APPROVE" | "DENY"}`.

**4. PENDING_RAI**
- **Trigger:** `TPA_PROCESSOR` initiates `POST /api/claims/{id}/rai` with `{"request_note": "string"}`.
- **Action:** Clinic must respond via `POST /api/claims/{id}/rai-response` with `{"response_note": "string"}`. Returns claim to `UNDER_REVIEW`. No 14-day expiry cron jobs required for MVP.

**5. FRAUD_FLAG**
- **Trigger:** Auto-assigned if `fraud_score >= 0.70`. 
- **Action:** Claim isolated for `TPA_FRAUD_ANALYST`. They use `POST /api/tpa/fraud/{id}/confirm` (→ DENIED) or `POST /api/tpa/fraud/{id}/clear` (→ UNDER_REVIEW).

**6. APPROVED**
- **Trigger:** Processor approval. Terminal state.

**7. DENIED**
- **Trigger:** Processor denial or Fraud confirmation. Terminal state. Clinic is presented with an "Appeal" button.

---

## SECTION E — RAI & APPEALS 

To avoid complex multi-table structures for the Hackathon, RAI notes and Appeal notes are tracked using a single `action_notes` table.

**Table: `action_notes`**
- `id` TEXT PK UUID
- `claim_id` TEXT FK → claims.id
- `user_id` TEXT FK → users.id
- `action_type` TEXT (Enum: `RAI_REQUEST`, `RAI_RESPONSE`, `APPEAL`)
- `note_text` TEXT NOT NULL
- `created_at` TEXT DEFAULT datetime('now')

**Appeal Logic:**
If status is `DENIED`, Clinic triggers `POST /api/claims/{id}/appeal` with `{"appeal_reason": "text"}`.
The endpoint inserts an `action_notes` row (type=`APPEAL`), and simply updates the claim status back to `UNDER_REVIEW`. The `TPA_PROCESSOR` re-evaluates the claim, seeing the appeal text appended to the claim history. No strict 30-day timers.

---

## SECTION F — SYNTHETIC DATA SEEDING

**Endpoint:** `POST /api/demo/seed` (SYSTEM_ADMIN only).
Idempotent. Drops/recreates demo users and claims.

**Demo Users Created (Password: `Demo@123`):**
- `clinic@demo.my` (`CLINIC_USER`, tenant: `clinic-alpha`)
- `processor@demo.my` (`TPA_PROCESSOR`, tenant: `tpa-omega`)
- `fraud@demo.my` (`TPA_FRAUD_ANALYST`, tenant: `tpa-omega`)
- `admin@demo.my` (`SYSTEM_ADMIN`, no tenant)

**Demo Scenarios Pre-loaded:**
1. **Clean STP Claim:** Status `APPROVED` (fraud_score 0.05).
2. **Flagged for Fraud:** Status `FRAUD_FLAG` (fraud_score 0.85, inflated amounts, duplicate IP pattern).
3. **RAI Required:** Status `PENDING_RAI` (missing referral letter).
4. **Duplicate:** Status `DENIED` (duplicate of claim 1).

---

## SECTION G — AUDIT LOG & SECURITY (JUDGING CRITERIA)

To satisfy the 6% Integration Security criteria without over-engineering DB triggers:

**Table: `audit_logs`**
- `id` TEXT PK UUID
- `timestamp` TEXT DEFAULT datetime('now', '+8 hours')
- `user_id` TEXT FK → users.id
- `action` TEXT NOT NULL (e.g., `LOGIN`, `CLAIM_SUBMITTED`, `STATUS_CHANGED_TO_APPROVED`)
- `target_id` TEXT nullable (e.g., claim_id)

**Implementation:**
A helper `log_audit(db, user_id, action, target_id)` MUST be invoked inside the API routes for every `POST`/`PUT`/`DELETE` request. The `SYSTEM_ADMIN` portal provides a read-only data grid of this table.

---

## SECTION H — TOKEN EFFICIENCY (JUDGING CRITERIA)

To satisfy the 4% Token Efficiency criteria, explicit tracking is required:

1. **Table: `token_usage`**
   - `id` TEXT PK UUID
   - `claim_id` TEXT FK
   - `prompt_tokens` INTEGER
   - `completion_tokens` INTEGER
   - `total_tokens` INTEGER
   - `cost_myr` REAL (computed based on active GLM pricing)

2. **Backend Requirement:** `glm_client.py` MUST parse the `usage` object from the OpenAI/GLM API response and insert a row into `token_usage` for every single AI generation. 
3. **Display:** The `TPA_PROCESSOR` claim detail view includes a tiny "Token Cost: RM X.XX" pill to transparently demonstrate efficiency to the judges.
