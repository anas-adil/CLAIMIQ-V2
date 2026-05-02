# ClaimIQ Bug Audit — Implementation Plan

## Summary

Full read of the codebase complete. Three confirmed bugs and several logic errors found. Fixes are ordered by severity.

---

## Bug 1 — Login Is Completely Broken

**Root cause identified:** `app.js` has a **duplicate `handleHash()` function body** that leaks outside the function (lines 140–151). The code after the closing `}` on line 138 is unreachable orphan code that runs at module load-time **before** the DOM is ready, causing a `null` reference crash on `document.getElementById("btnLogout")`. This crash silences all subsequent initialisation including the login form's `doLogin()` call.

Additionally, `loadClaims()` (line 389) calls `fetch(url)` directly **without the auth header**, so claims will return 401 after login.

**Fixes:**
- Remove the orphan duplicate block (lines 140–151) from `app.js`.
- Fix `loadClaims()` to use `apiFetch()` instead of bare `fetch()`.

---

## Bug 2 — Full Nav Visible on Login Page

**Root cause identified:** `index.html` line 200 sets `topNav.style.display = "none"` inside `DOMContentLoaded`, but then `handleHash()` (called immediately after) calls `applyRoleNav()`, which resets it to `"flex"` for non-login hash. On initial page load with no hash, `window.location.hash` is `""`, which `normalizeViewFromHash` maps to `"login"`, so `applyRoleNav()` should hide the nav — **BUT** the orphan crash from Bug 1 means `handleHash()` never ran properly.

Once Bug 1 is fixed, the nav hide logic should work, **but** `applyRoleNav()` also fails to explicitly hide/show the `global-search` and nav-actions independently. The entire `<nav>` is toggled, so fixing Bug 1 fixes Bug 2 as well. The brand logo remains inside the nav and will disappear too — that's acceptable per spec (brand logo "may remain").

However: navigating directly to `/` without a hash lands on `""` → maps to `"login"` correctly. Navigating directly to e.g. `#/portal/dashboard` while logged out: `handleHash()` catches this and redirects to `#/portal/login`. ✓

---

## Bug 3 — Nav Does Not Filter by Role After Login

**Root cause identified:** `applyRoleNav()` IS implemented correctly in the fixed code — it hides nav items not in `ROLE_ALLOWED_VIEWS`. **BUT** there are two issues:

1. The `btnSeedDemo` visibility is set correctly for `SYSTEM_ADMIN` only.
2. `ROLE_ALLOWED_VIEWS` gives `CLINIC_USER` access to `claims` and `denials` — which is **wrong** for a clinic user in a real TPA. A clinic user should only see their own GP portal and claim submission. They should NOT see the full claims queue (which shows all clinics' claims from the TPA's perspective).

**However**, the backend `_tenant_filter` does correctly scope clinic users to their own `clinic_id` — so the data is safe, but the UX is misleading. The nav links for `claims` and `denials` from a clinic's POV should remain but be re-labelled, OR we remove them entirely and make the GP portal the entry point for clinic's own claims.

Per real-world logic: a clinic user sees their own claims through the GP Portal. They do NOT use the TPA's claims queue view. Fix: remove `claims` and `denials` from `CLINIC_USER` allowed views.

---

## Additional Bugs Found During Audit

### Bug 4 — Duplicate `seedDemo()` function
`app.js` has `seedDemo()` defined **twice** (lines 1005–1028 and 1037–1068). JavaScript silently uses the second definition. The second one calls `window.location.reload()` which destroys state. Remove the first definition and keep the second (better) one.

### Bug 5 — `loadClaims()` uses bare `fetch()` without auth header
Line 389: `const res = await fetch(url).then(r => r.json())` — this will always 401 after login because no `Authorization` header is sent. Must use `apiFetch()`.

### Bug 6 — `handleHash()` orphan code causes crash at startup
Lines 140–151 are outside any function. They run at module parse time (script load), before DOM is ready, causing `document.getElementById("btnLogout")` to throw `null` reference. This is the **primary cause of the silent login failure**.

### Bug 7 — `submitClaim()` sends wrong payload to `/api/claims/submit`
The frontend `submitClaim()` sends `raw_text`, `patient_name`, `patient_ic`, `clinic_name`, `visit_date`, `total_amount_myr` — but the backend `ClaimSubmission` model expects `patient_ic` (with regex `^\d{6}-\d{2}-\d{4}$`), `patient_name`, `visit_date`, `diagnosis_codes` (List[str]), `line_items` (List[LineItem]), `total_amount`. The frontend doesn't construct `diagnosis_codes` or `line_items`, so this will always fail with a 422. This is a submit pipeline mismatch — the frontend submit path calls `/api/claims/submit` which is the structured API endpoint, but the payload doesn't match. Fix: the frontend should call the process endpoint or construct a valid payload.

### Bug 8 — `submitClaim()` then calls `/api/claims/process/{claimId}` which doesn't exist
After submitting, line 731 calls `/api/claims/process/${claimId}` — this endpoint does not exist in `api_server.py`. This will 404. The processing happens automatically in `api_server.py` after submit (line 154: `claims_processor.process_claim(...)`).

### Bug 9 — Appeal response references `res.appeal_id` and `res.rebuttal` which don't exist
The backend `appeal_claim` endpoint returns `{"status": "UNDER_REVIEW"}`. The frontend tries to render `res.appeal_id` and `res.rebuttal.rebuttal_body` — these fields don't exist in the response. The appeal modal will show broken output.

### Bug 10 — `notifBtn` listener attached before DOMContentLoaded
Line 1034: `document.getElementById("notifBtn").addEventListener(...)` runs at module load time (outside DOMContentLoaded). If the element doesn't exist yet, this throws. Should be moved inside DOMContentLoaded.

### Bug 11 — Analytics routes (`/api/analytics/*`) have no role restriction
`/api/analytics/clinics`, `/api/analytics/fraud-heatmap`, `/api/analytics/mc-patterns`, `/api/analytics/weekly-report` all use `get_current_user` (any authenticated user). A `CLINIC_USER` should NOT see cross-clinic analytics or fraud heatmaps of other clinics. The `fraud-heatmap` applies `_tenant_filter` correctly, but `/api/analytics/clinics` returns all clinics to all users. Fix: restrict `/api/analytics/clinics` and `/api/analytics/mc-patterns` to TPA roles only.

### Bug 12 — Review action (Approve/Deny) visible to CLINIC_USER in claim modal
The claim detail modal shows "Safety Gate Review" buttons (Approve/Deny) whenever status is `PENDING_APPROVAL` or `PENDING_DENIAL`. A clinic user can see this. The backend `/api/claims/{claim_id}/review` correctly requires `TPA_PROCESSOR` role, so the API is safe, but the button should not appear for clinic users.

### Bug 13 — `line_items` dict() call on Pydantic model
`api_server.py` line 146: `json.dumps([item.dict() for item in body.line_items])` — `.dict()` is deprecated in Pydantic v2. Should be `.model_dump()`. This may cause a warning or error depending on Pydantic version.

---

## Proposed Changes

### `execution/frontend/app.js`

#### Fix 1: Remove orphan duplicate code (lines 140–151) — fixes silent crash
#### Fix 2: Fix `loadClaims()` to use `apiFetch()` — fixes auth on claims fetch  
#### Fix 3: Remove `claims` and `denials` from `CLINIC_USER` ROLE_ALLOWED_VIEWS
#### Fix 4: Remove first `seedDemo()` duplicate (lines 1005–1028)
#### Fix 5: Move `notifBtn` listener inside DOMContentLoaded
#### Fix 6: Fix `submitClaim()` — remove call to non-existent `/process/` endpoint, construct valid payload
#### Fix 7: Fix appeal modal — handle response correctly (show status message, not missing fields)
#### Fix 8: Hide "Safety Gate Review" buttons from CLINIC_USER

### `execution/api_server.py`

#### Fix 9: Restrict `/api/analytics/clinics` and `/api/analytics/mc-patterns` to TPA roles
#### Fix 10: Fix `item.dict()` → `item.model_dump()` (Pydantic v2 compat)

---

## Verification Plan

- Start the server
- Login with all 4 accounts and confirm correct redirect + nav items visible
- Attempt wrong password — confirm error shown
- Logout and navigate directly to protected route — confirm redirect to login
- Submit a claim as clinic@demo.my — confirm it works
- As processor@demo.my, approve/deny a claim
- As fraud@demo.my, confirm fraud queue visible, claim approve/deny NOT visible
- As admin@demo.my, confirm all nav items + Seed Demo visible
