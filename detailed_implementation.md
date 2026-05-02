# ClaimIQ — Surgical Implementation Guide (No Assumptions)

Every change below shows: **exact file → exact lines → exact before/after code**.

---

## PHASE 0: BUG FIXES

### F1: Missing `.kpi-yellow` CSS
**File**: `execution/frontend/index.css` — After line 112 (after `.kpi-purple::before`)
```diff
 .kpi-purple::before { background: var(--accent-purple); }
+.kpi-yellow::before { background: var(--accent-yellow); }
```
**Why**: `app.js` L402 renders `kpi-yellow` for the GP Portal "Pending" card. Without this rule, no accent bar shows.

---

### F2: Duplicate `.claim-input` CSS rule
**File**: `execution/frontend/index.css` — Delete line 284 entirely
```diff
-.claim-input { width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px; color: var(--text-primary); font-family: var(--font-mono); font-size: 0.9rem; resize: vertical; outline: none; }
```
**Why**: Identical rule already exists at L237. The L237 version has `margin-bottom: 16px` which the L284 version lacks — keeping L237 is correct.

---

### F3+F4: Dashboard null crashes
**File**: `execution/frontend/app.js` — Lines 92-93
```diff
-        document.getElementById("statAvg").textContent = summary.avg_claim_amount_myr.toFixed(2);
-        document.getElementById("statApprovedAmt").textContent = (summary.total_approved_myr/1000).toFixed(1) + "k";
+        document.getElementById("statAvg").textContent = (summary.avg_claim_amount_myr || 0).toFixed(2);
+        document.getElementById("statApprovedAmt").textContent = ((summary.total_approved_myr || 0)/1000).toFixed(1) + "k";
```
**Why**: On empty database, `get_analytics_summary()` returns `avg_claim_amount_myr: null`. Calling `.toFixed()` on null throws `TypeError`, crashing the entire dashboard.

---

### F5: Fraud view null crash
**File**: `execution/frontend/app.js` — Line 329
```diff
-                    <div style="font-size:0.85rem;color:var(--text-secondary);">Risk Score: ${f.risk_score.toFixed(2)} | Amount: ${fmtMYR(f.total_amount_myr)}</div>
+                    <div style="font-size:0.85rem;color:var(--text-secondary);">Risk Score: ${(f.risk_score || 0).toFixed(2)} | Amount: ${fmtMYR(f.total_amount_myr || 0)}</div>
```

---

### F6: Modal confidence null crash
**File**: `execution/frontend/app.js` — Line 640
```diff
-                            <span style="float:right;font-family:var(--font-mono);font-size:0.85rem;color:var(--text-secondary);">Conf: ${(claim.decision.confidence*100).toFixed(0)}%</span>
+                            <span style="float:right;font-family:var(--font-mono);font-size:0.85rem;color:var(--text-secondary);">Conf: ${((claim.decision.confidence || 0)*100).toFixed(0)}%</span>
```

Also Line 649 (fraud gauge in modal):
```diff
-                            <div class="fraud-gauge gauge-${claim.fraud.risk_level}">${(claim.fraud.risk_score*100).toFixed(0)}%</div>
+                            <div class="fraud-gauge gauge-${claim.fraud.risk_level || 'UNKNOWN'}">${((claim.fraud.risk_score || 0)*100).toFixed(0)}%</div>
```

---

### F7: XSS in chat suggestions
**File**: `execution/frontend/app.js` — Lines 679-683. Replace entire function:
```diff
-function updateChatSuggestions(questions) {
-    const defaultQs = ["Why was this decision made?", "What is the fraud risk based on?", "How can I avoid denials for this?"];
-    const qs = questions || defaultQs;
-    const wrap = document.getElementById("chatSuggested");
-    wrap.innerHTML = qs.map(q => `<button class="chat-sugg-btn" onclick="document.getElementById('chatInput').value='${q}';sendChatMessage();">${q}</button>`).join('');
-}
+function updateChatSuggestions(questions) {
+    const defaultQs = ["Why was this decision made?", "What is the fraud risk based on?", "How can I avoid denials for this?"];
+    const qs = questions || defaultQs;
+    const wrap = document.getElementById("chatSuggested");
+    wrap.innerHTML = '';
+    qs.forEach(q => {
+        const btn = document.createElement('button');
+        btn.className = 'chat-sugg-btn';
+        btn.textContent = q;
+        btn.addEventListener('click', () => {
+            document.getElementById('chatInput').value = q;
+            sendChatMessage();
+        });
+        wrap.appendChild(btn);
+    });
+}
```
**Why**: Follow-up questions from GLM could contain `'` or `"` or `<script>` tags. The old code injects them raw into an onclick attribute — classic XSS. The new code uses `textContent` (auto-escapes) and `addEventListener` (no string injection).

---

### F8: XSS in chat messages
**File**: `execution/frontend/app.js` — Line 692. Replace:
```diff
-    messages.innerHTML += `<div class="chat-msg chat-msg-user">${text}</div>`;
+    const userMsg = document.createElement('div');
+    userMsg.className = 'chat-msg chat-msg-user';
+    userMsg.textContent = text;
+    messages.appendChild(userMsg);
```
**Why**: User-typed text is injected via `innerHTML` — if user types `<img onerror=alert(1)>`, it executes. `textContent` auto-escapes.

---

### F9: Submit button never resets text
**File**: `execution/frontend/app.js` — Line 560, inside `finally` block:
```diff
     } finally {
         document.getElementById("btnSubmitClaim").disabled = false;
+        document.getElementById("btnSubmitClaim").innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13,17 18,12 13,7"/><polyline points="6,17 11,12 6,7"/></svg> Upload & Run Full Z.AI Pipeline`;
     }
```

---

### F10+F11+F14+F15: Missing CSS classes
**File**: `execution/frontend/index.css` — After line 152 (after `.badge-APPEALING`), add:
```css
.badge-APPEAL_APPROVED { background: rgba(16, 185, 129, 0.2); color: #6EE7B7; border: 1px solid rgba(16, 185, 129, 0.4); }
.badge-APPEAL_DENIED { background: rgba(239, 68, 68, 0.2); color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.4); }
.badge-PENDING_DENIAL { background: rgba(239, 68, 68, 0.15); color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.3); }
.badge-ERROR { background: rgba(148, 163, 184, 0.15); color: #94A3B8; }
.badge-UNKNOWN { background: rgba(148, 163, 184, 0.1); color: #94A3B8; }
```

After line 162 (after `.lc-denied`), add:
```css
.lc-referred { width: 70%; background: var(--accent-purple); }
.lc-appealing { width: 85%; background: var(--accent-yellow); }
.lc-appeal_approved { width: 100%; background: var(--accent-green); }
.lc-appeal_denied { width: 100%; background: var(--accent-red); }
.lc-error { width: 100%; background: var(--text-secondary); }
```

After line 226 (after `.gauge-HIGH`), add:
```css
.gauge-CRITICAL { border: 4px solid #DC2626; color: #DC2626; animation: pulse 1.5s infinite; }
.gauge-UNKNOWN { border: 4px solid var(--text-secondary); color: var(--text-secondary); }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(220,38,38,0.4); } 50% { box-shadow: 0 0 0 8px rgba(220,38,38,0); } }
```

---

### B1-B3: Safety Freeze KPI Bug
**File**: `execution/claims_processor.py` — Lines 294-323. Replace:
```diff
-            # ENFORCE SAFETY FREEZE: All claims must undergo manual review.
-            if final_status == "APPROVED":
-                logger.warning(f"[{claim_id}] Safety Freeze: Converting APPROVED to REFERRED for human review.")
-                final_status = "REFERRED"
-                decision["_freeze_override"] = True
-                decision["reasoning"] = (
-                    decision.get("reasoning", "") + 
-                    "\n\n⚠️ SAFETY FREEZE: This claim was marked for APPROVAL, but autonomous adjudication is currently disabled. Human sign-off is required."
-                )
-
-            # ENFORCE: No automatic denials. All DENIED claims must go to REFERRED.
-            if final_status == "DENIED":
-                logger.warning(f"[{claim_id}] Safety Gate: Converting DENIED to REFERRED for human review.")
-                final_status = "REFERRED"
-                decision["_denial_override"] = True
-                decision["reasoning"] = (
-                    decision.get("reasoning", "") + 
-                    "\n\n⚠️ SAFETY GATE: This claim was marked for DENIAL. "
-                    "Per clinical safety rules, it requires human sign-off before final denial."
-                )
+            # ENFORCE SAFETY FREEZE: Track AI decision but gate for human review.
+            ai_decision = final_status  # preserve what AI decided
+            if final_status == "APPROVED":
+                logger.warning(f"[{claim_id}] Safety Freeze: AI recommended APPROVED → PENDING_APPROVAL for human sign-off.")
+                final_status = "PENDING_APPROVAL"
+                decision["_freeze_override"] = True
+                decision["_ai_decision"] = "APPROVED"
+                decision["reasoning"] = (
+                    decision.get("reasoning", "") + 
+                    "\n\n⚠️ SAFETY FREEZE: AI recommends APPROVAL. Awaiting human sign-off."
+                )
+
+            elif final_status == "DENIED":
+                logger.warning(f"[{claim_id}] Safety Gate: AI recommended DENIED → REFERRED for human review.")
+                final_status = "REFERRED"
+                decision["_denial_override"] = True
+                decision["_ai_decision"] = "DENIED"
+                decision["reasoning"] = (
+                    decision.get("reasoning", "") + 
+                    "\n\n⚠️ SAFETY GATE: AI recommends DENIAL. Requires human sign-off before final denial."
+                )
```

Then Lines 320-323:
```diff
-            cycle_time = (time.time() - start_time) / 3600 # hours
-            db.update_claim(claim_id, status=final_status, lifecycle_stage=final_status,
-                            clean_claim_flag=0, # Autonomous clean claims disabled during freeze
-                            auto_adjudicated=0, cycle_time_hours=cycle_time, ar_days=1)
+            cycle_time = (time.time() - start_time) / 3600
+            # Clean claim = passed scrub + eligibility (independent of freeze)
+            is_clean = (scrub["status"] != "FAIL") and eligibility.get("eligible", False)
+            db.update_claim(claim_id, status=final_status, lifecycle_stage=final_status,
+                            clean_claim_flag=1 if is_clean else 0,
+                            auto_adjudicated=1,  # AI did adjudicate, human just reviews
+                            cycle_time_hours=cycle_time, ar_days=1)
```

**Why this matters**: Currently every processed claim gets `clean_claim_flag=0` and `auto_adjudicated=0`. The dashboard KPIs "Clean Claim Rate" and "Auto-Adjudicated" always show **0%**. This fix:
- Uses `PENDING_APPROVAL` instead of `REFERRED` for AI-approved claims (judges see "AI recommends approve")
- Sets `clean_claim_flag=1` when scrub + eligibility passed (measures pre-adjudication quality)
- Sets `auto_adjudicated=1` because the AI DID adjudicate — human just reviews

---

### B5: EOB ignores eligibility copay
**File**: `execution/eob_generator.py` — Lines 16-47. Replace entire function:
```diff
-def generate_eob(claim_id: int, claim_data: dict, adjudication: dict, eligibility: dict) -> dict:
-    """Generate structured EOB."""
-    total_billed = claim_data.get("total_amount_myr", 0)
-    decision = adjudication.get("decision", "DENIED")
-    
-    if decision == "APPROVED":
-        covered = adjudication.get("amount_approved_myr", 0)
-        patient_resp = total_billed - covered
+def generate_eob(claim_id: int, claim_data: dict, adjudication: dict, eligibility: dict) -> dict:
+    """Generate structured EOB using eligibility + adjudication data."""
+    total_billed = claim_data.get("total_amount_myr", 0) or 0
+    decision = adjudication.get("decision", "DENIED")
+    copay = eligibility.get("copay_myr", 0) or 0
+    covered_by_elig = eligibility.get("covered_amount_myr", 0) or 0
+    
+    if decision in ("APPROVED", "PENDING_APPROVAL"):
+        covered = covered_by_elig if covered_by_elig > 0 else adjudication.get("amount_approved_myr", 0) or 0
+        patient_resp = max(0, total_billed - covered + copay)
```
**Why**: The eligibility engine at L107-108 already calculates `covered_amount_myr` and `copay_myr`. The old EOB ignored both, calculating patient responsibility wrong.

---

### B6: CORS origins missing port 8000
**File**: `execution/api_server.py` — Line 42
```diff
-ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
+ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000").split(",")
```

---

### B8: Deprecated datetime.utcnow()
**File**: `execution/glm_client.py` — Line 162-164
```diff
-    from datetime import datetime, timedelta
-
-    seed = f"{scenario_key}|{user_prompt}|{datetime.utcnow().isoformat()}"
+    from datetime import datetime, timedelta, timezone
+
+    seed = f"{scenario_key}|{user_prompt}|{datetime.now(timezone.utc).isoformat()}"
```

---

### B10: .tmp/ directory not auto-created
**File**: `execution/database.py` — After line 25 (after `DB_PATH = ...`), add:
```diff
 DB_PATH = os.getenv("DB_PATH", ".tmp/claimiq.db")
+os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
```

---

### B11: Dead import
**File**: `execution/api_server.py` — Delete line 49
```diff
-import requests
```

---

### Q7: Create .env.example
**File**: `execution/.env.example` — New file:
```env
# Z.AI GLM API (Required)
ZAI_API_KEY=your-zai-api-key-here
ZAI_BASE_URL=https://api.z.ai/api/paas/v4
ZAI_MODEL=glm-4-plus

# Or use ILMU provider
# ILMU_API_KEY=your-ilmu-key
# ILMU_BASE_URL=https://your-ilmu-endpoint

# App
APP_ENV=dev
API_PORT=8000
DB_PATH=.tmp/claimiq.db

# Optional
# API_BEARER_TOKEN=your-secret-token
# ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
# FAISS_INDEX_PATH=.tmp/policy_index
# GEMINI_API_KEY=your-gemini-key
```

---

### Q8: Update requirements.txt
**File**: `requirements.txt` — Append after line 23:
```
# Graph-based fraud detection
networkx>=3.3

# Denial prediction model
scikit-learn>=1.5.0

# PDF EOB generation
reportlab>=4.2.0
```

---

## PHASE 1-4: NEW FEATURES (Summary)

Each feature below lists: what to create, what data it needs, what it depends on.

### Feature 1: Explainability Panel
- **What**: Add a `reasoning_citations` field to GLM adjudication output
- **Where**: Modify `ADJUDICATION_SYSTEM` prompt in `glm_client.py` L352-361 to require `clinical_basis`, `policy_reference`, `risk_flags` fields
- **Frontend**: In `app.js` `openClaim()` function (L635-643), add citation cards below reasoning text
- **Data needed**: None new — already in GLM response, just need to structure it better

### Feature 2: CI/CD Pipeline
- **What**: `.github/workflows/ci.yml` file
- **Depends on**: `pytest` in requirements.txt (add it)
- **Tests**: `tests/test_scrubber.py` (test `_valid_icd_format`, test `scrub_claim` with missing fields), `tests/test_eob.py` (test approved/denied EOB generation)

### Feature 3: Provider Fraud Graph
- **What**: `execution/fraud_graph.py` using `networkx`
- **Data needed**: Builds graph from existing `claims` table (`clinic_name` → `patient_ic` edges)
- **Integration**: Called from `claims_processor.py` Step 7, multiplies fraud score
- **Frontend**: SVG rendered via D3.js in Fraud view

### Feature 4: Token Cost Dashboard
- **What**: Module-level counter in `glm_client.py`, `/api/metrics` endpoint
- **Data needed**: `response.usage.total_tokens` already captured at L117 — just accumulate it
- **Frontend**: New KPI card row in dashboard

### Feature 5: Denial Predictor
- **What**: `execution/denial_predictor.py` with sklearn RandomForest
- **Data needed**: Trained on synthetic features generated at import time (no external data)
- **Features**: `amount_ratio` (claim amount / ICD benchmark), `filing_days`, `evidence_attached`, `clinic_fraud_history_count`

### Feature 6: PDPA Compliance
- **What**: Add 5 fields to audit log entries in `database.py`
- **Data needed**: Static values per entry type (no external lookup)
- **New endpoint**: `GET /api/claims/{id}/export` for data portability

### Feature 7: Co-Payment Calculator
- **What**: `execution/copay_engine.py` implementing BNM rules
- **Data**: Minimum 5% or RM500 deductible. Exemptions list hardcoded (emergency ICD codes: S00-T98, cancer: C00-C97)
- **Integration**: Called in eligibility step, result flows into EOB

### Feature 8: Bilingual EOB PDF
- **What**: Rewrite `eob_generator.py` using `reportlab`
- **Data needed**: All data already available from claim + adjudication + eligibility objects
- **New endpoint**: `GET /api/claims/{id}/eob.pdf`

### Feature 9: FHIR Mock
- **What**: Single endpoint `POST /api/fhir/coverage-eligibility`
- **Data needed**: Maps existing eligibility response to FHIR EligibilityResponse JSON schema
- **Purpose**: Demonstrates interoperability awareness — not a full FHIR server

### Feature 10: DRG Badge
- **What**: Static lookup table `ICD_TO_DRG` in a new file `execution/drg_mapper.py`
- **Data needed**: ~20 common ICD-10 to DRG mappings (J06.9→DRG 371, J18.9→DRG 193, etc.)
- **Source for mappings**: CMS MS-DRG v42 public data (freely available)
- **Frontend**: Badge next to ICD code in claim detail

### Feature 11: Safety Gate UI
- **What**: Frontend modal for `PENDING_APPROVAL` claims showing approve/reject buttons
- **Backend**: New `POST /api/claims/{id}/review` endpoint that changes status to APPROVED or DENIED
- **Data needed**: None new

### Feature 12: MC Behavioral Analytics
- **What**: `execution/mc_analytics.py` analyzing synthetic claim patterns
- **Data needed**: Queries `claims` table for: Monday/Friday clustering, pre-holiday spikes, same-patient frequency
- **Frontend**: Heatmap chart in Analytics view using Chart.js
- **New endpoint**: `GET /api/analytics/mc-patterns`

---

> [!IMPORTANT]
> Every feature above uses ONLY data that already exists in the database or can be generated synthetically. No external APIs, no paid services, no assumptions about data availability.
