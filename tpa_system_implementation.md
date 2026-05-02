# ClaimIQ — Exhaustive System Planning Document
**Malaysian Private Healthcare & TPA Claims Intelligence Platform**
*Version 1.1 | May 2026 | For internal planning use only*

---

## SECTION 1 — REAL-LIFE WORKFLOW MAPPING

### Malaysian Healthcare Context (Read First)
Malaysian private healthcare operates on a panel clinic model. Employers contract with TPAs (PMCare, Etiqa TPA, AIA, Bupa, etc.) who maintain networks of approved ("panel") clinics. When an employee visits a panel clinic, the clinic bills the TPA directly — the patient pays little or nothing at point of care (cashless). Non-panel visits require out-of-pocket payment and reimbursement claims. This is fundamentally different from Western fee-for-service models where billing goes through insurers post-visit. The TPA sits between employer, clinic, and insurer, and is the primary adjudication party ClaimIQ serves.

---

### Step 1 — Patient Arrives at Clinic or Hospital
**Who performs it:** Patient; Front Desk Registration Staff

**Documents and information involved:**
- MyKad (Malaysian National Identity Card) — 12-digit IC number is the universal patient identifier. Format: YYMMDD-PB-XXXX where PB is the state/place of birth code. This is used for all eligibility lookups.
- Corporate panel card (physical or digital) issued by employer/TPA
- Insurance card (for individual policy holders)
- Letter of Guarantee (LOG) for inpatient/specialist cases — a pre-authorisation document issued by TPA before the procedure
- Referral letter (if referred from GP to specialist or from clinic to hospital)

**System touchpoints:**
- Front desk queries ClaimIQ eligibility API using IC number or panel card number
- System returns: policy status (active/inactive/suspended), benefit limits remaining, co-pay amount if any, panel status of the clinic, any pre-existing condition flags, and whether a LOG is required for this visit type

**What can go wrong:**
- Policy lapsed due to non-payment of premium but system not yet updated.
- Patient presents at a non-panel clinic believing it is panel.
- Employee has recently resigned or been terminated — HR has not yet deregistered them from the corporate scheme.
- IC number entered incorrectly.
- Patient is a dependent (spouse/child) rather than the primary policy holder — dependent ID must be linked to primary IC.

**Malaysian-specific norms:**
- MyKad is mandatory by law. Foreigners use passport numbers. ClaimIQ supports both.
- PDPA (Personal Data Protection Act 2010/2024 Amendment) requires explicit patient consent before data processing. ClaimIQ must log that consent was given.
- BNM Circular on Medical and Health Insurance requires TPAs to maintain live panel lists. Panel status must be verified in real time.

---

### Step 2 — Registration and Insurance/Corporate Card Verification
**Who performs it:** Front Desk / Registration Staff; ClaimIQ system (automated)

**Documents involved:**
- MyKad scan or manual entry
- Panel card number
- Existing LOG number (for inpatient)

**System touchpoints:**
- ClaimIQ Eligibility Module: returns eligibility status, benefit class, annual limit, balance remaining, co-pay rules, exclusions flagged.
- LOG verification: checks LOG validity, matching procedure, and facility.

**What can go wrong:**
- LOG presented is expired.
- LOG was issued for a different procedure.
- Patient's annual limit is exhausted — system must alert front desk.
- Dependent registration is missing.
- System downtime — fallback to manual verification via phone with TPA.

**Malaysian-specific norms:**
- Pre-authorisation (PA) or LOG is a hard requirement for all inpatient admissions in Malaysia.
- PA turnaround time is typically 2–4 hours for routine cases, up to 24 hours for complex surgical cases. Emergency admissions are exempt but require 24-hour notification.
- September 2024 BNM mandate for minimum 5% or RM500 deductible co-payment must be calculated here.

---

### Step 3 — Consultation, Procedure, Diagnosis
**Who performs it:** Clinic Doctor / Treating Physician; Nursing Staff

**Documents involved:**
- Medical notes (SOAP format)
- Diagnosis — ICD-10-CM codes (hospitals) or free-text diagnosis (GPs).
- Procedure codes — MMA (Malaysian Medical Association) fee schedule codes or proprietary TPA schedules.
- MC (Medical Certificate) — duration and frequency are key fraud signals.
- Lab results, imaging reports, referral letters, drug dispensing records.

**System touchpoints:**
- Doctor does not interact with ClaimIQ directly at this stage. Clinic's EMR pushes codes to ClaimIQ.

**What can go wrong:**
- Diagnosis code mismatch by billing staff.
- Upcoding or unbundling (fraud vectors).
- Prescribing non-formulary medications.
- MC duration exceeds clinical justification.

**Malaysian-specific norms:**
- ICD-10 is the MOH standard, but GP compliance varies. ClaimIQ must handle mapping.
- MMA publishes a recommended fee schedule, but TPAs negotiate fee caps with panel clinics.
- Drug dispensing records must comply with the Poisons Act 1952.

---

### Step 4 — Clinic Staff Creates and Submits the Claim
**Who performs it:** Clinic Billing/Claims Officer

**Documents and information compiled:**
- Demographics, Visit date/time, Attending physician MMC number, Clinic MOH registration number.
- Diagnosis codes, Procedure codes, Itemised bill, MC details.
- Supporting docs: lab reports, imaging, consent forms, discharge summary.

**System touchpoints:**
- ClaimIQ Claim Submission UI.
- Automated scrubbing: mandatory fields, duplicate check, fee schedule check, formulary check.
- Status moves to `SUBMITTED`.

**What can go wrong:**
- Claim submitted past the submission deadline (usually 30–60 days in Malaysia).
- Missing mandatory attachments.
- Duplicate submission.
- MMC number expired.

**Malaysian-specific norms:**
- MOH requires clinics to retain patient records for 7 years.
- Claims from corporate schemes are subject to LHDN tax treatment as employment benefits.

---

### Step 5 — Claim Travels to TPA
**Who performs it:** ClaimIQ system; TPA Claims Processor

**What happens:**
- ClaimIQ routes the claim to the correct TPA queue.
- Automated pre-screening runs: duplicate detection, sanction list check, fraud score computation.

**What can go wrong:**
- Routing error (e.g., patient has multiple policies).
- Claim arrives without mandatory attachments (triggers auto-RAI).

**Malaysian-specific norms:**
- TPAs handling medical claims must be licensed under the Financial Services Act 2013 (requires strict data security and BNM reporting).

---

### Step 6 — TPA Adjudicates (Manual or Automated)
**Who performs it:** ClaimIQ AI engine (automated first pass); TPA Claims Processor; TPA Senior Adjudicator

**Adjudication checks performed:**
1. Policy coverage verification.
2. Waiting period check (Standard in Malaysia: 30 days general, 120 days specified illness, 12 months pre-existing).
3. Pre-existing condition exclusion.
4. Annual/lifetime limit check.
5. Co-pay application.
6. Fee reasonableness (against MMA/TPA schedule).
7. Medical necessity.
8. Clinical coding review.
9. Panel status confirmation.
10. LOG/PA compliance.
11. Fraud score review.

**Automated vs manual:**
- Low-risk GP claims (< RM 500) go to Straight-Through Processing (STP).
- High-risk, exclusion triggers, or inpatient claims route to human review.

**Malaysian-specific norms:**
- Pre-existing conditions rely heavily on non-disclosure clauses; discovery at claim time allows denial/voiding.
- BNM guidelines on fair treatment dictate claims turnaround times.
- Takaful policies (Islamic insurance) follow tabarru concepts; ClaimIQ flags takaful vs conventional.

---

### Step 7 — Approval, Denial, or Request for Additional Information (RAI)
**Approval path:** Status `APPROVED`. EOB generated.
**Denial path:** Status `DENIED` with specific CARC reason code. Denial letter generated.
**RAI path:** Status `PENDING_RAI`. specific documents requested. Deadline clock starts (14-21 days).

**Denial reason codes (Malaysian context):**
- PRE_EXIST, WAIT_PERIOD, NON_PANEL, NO_PA, LIMIT_EXCEEDED, NON_COVERED, LATE_SUBMISSION, INSUFF_DOCS, DUPLICATE, FRAUD_SUSPEND, POLICY_LAPSED, FORMULARY, FEE_EXCESS.

**What can go wrong:**
- Denial letter is vague (frequent complaint in Malaysia). ClaimIQ enforces clear plain-language mapping.
- Partial approval is not communicated clearly.

---

### Step 8 — Payment Disbursement
**Who performs it:** TPA Finance/Payment Officer; Bank systems

**How payment works in Malaysia:**
- Cashless panel claims: TPA pays clinic via batch bank transfer (IBG or DuitNow).
- Reimbursement claims: TPA pays patient directly.
- Co-pay collection: Patient pays clinic upfront. TPA pays the rest.

**System touchpoints:**
- ClaimIQ generates batch file. Finance officer approves. Status `PAID`.

**Malaysian-specific norms:**
- DuitNow and IBG are dominant.
- Clawback provisions exist in panel agreements allowing TPAs to offset future payments for discovered overpayments.

---

### Step 9 — Appeal If Denied
**Who performs it:** Clinic Billing Officer (on behalf of patient) or Patient.

**System touchpoints:**
- Submission through ClaimIQ Appeal Portal. Status `APPEAL_SUBMITTED`.

---

### Step 10 — Appeal Reviewed and Resolved
**Who performs it:** TPA Senior Adjudicator; TPA Medical Advisor.

**Process:**
- Appeal assigned to different Senior Adjudicator (Chinese Wall).
- Medical advisor consulted if clinical.
- Decision: `APPEAL_UPHELD` or `APPEAL_DISMISSED`.
- If dismissed, patient informed of right to escalate to BNM LINK or Ombudsman for Financial Services (OFS).

---

## SECTION 2 — ACTOR & ROLE INVENTORY

**1. Clinic Front Desk:** Runs eligibility, generates GL, collects co-pay. Cannot submit claims or see financials.
**2. Clinic Doctor:** Inputs diagnosis, attaches notes. Sees clinical history. Does not see TPA fraud scores.
**3. Clinic Billing Officer:** Submits claims, initiates appeals, responds to RAIs, views EOBs. Cannot see TPA adjudication rules.
**4. Clinic Admin/Owner:** Clinic-wide financial dashboard, manages staff, views panel agreements. Restricted to their own clinic's data.
**5. TPA Claims Processor (Junior):** Adjudicates assigned low-to-mid value claims, raises RAIs. Cannot approve > RM5000 or override "Critical" fraud flags.
**6. TPA Senior Adjudicator:** Reviews complex claims, overrides junior/AI decisions, reviews appeals. Refers to medical advisor.
**7. TPA Fraud Analyst:** Reviews fraud heatmaps and Provider Graphs. Recommends provider suspension. Cannot adjudicate claims. Interfaces with PIAM (Persatuan Insurans Am Malaysia) Fraud Intelligence System (FITS).
**8. TPA Finance Officer:** Generates payment batches, handles clawbacks via IBG/DuitNow. Cannot alter medical data.
**9. TPA Admin / Supervisor:** Manages SLA compliance, configures TPA rules, reassigns queues.
**10. Corporate HR:** Views aggregated utilisation and MC heatmaps. Enrols/terminates employees. Strictly restricted from viewing individual clinical diagnoses (PDPA compliance).
**11. Patient (Self-Service):** Submits out-of-pocket claims, views own EOBs and policy limits.
**12. ClaimIQ System Admin:** Platform IT. Manages TPA tenants. Accesses data only with strict audit logging for support purposes.

---

## SECTION 3 — PORTAL DESIGN PER ROLE
*(See full detailed breakdown in user prompt document for granular UI visibility matrix per role, specifically respecting Zero Cross-Contamination and PDPA).*

---

## SECTION 4 — CLAIM LIFECYCLE STATE MACHINE

**Statuses mapped to `claims_processor.py` database schema:**
1. `DRAFT`: Local to clinic, not submitted.
2. `SUBMITTED`: Clean submission, en route to TPA.
3. `RECEIVED`: Intake complete.
4. `PENDING_PA_VERIFICATION`: Awaiting LOG check.
5. `UNDER_REVIEW`: Active processing (by AI or human).
6. `PENDING_RAI`: Awaiting clinic docs.
7. `RAI_RECEIVED`: Clinic replied.
8. `PENDING_FRAUD_REVIEW`: Suspended for FWA investigation.
9. `PENDING_MEDICAL_OPINION`: Referred to clinical advisor.
10. `PENDING_APPROVAL`: AI approved; awaiting human safety gate.
11. `PENDING_DENIAL`: AI denied; awaiting human safety gate.
12. `APPROVED`: Fully approved.
13. `PARTIAL_APPROVAL`: Some line items denied.
14. `DENIED`: Fully denied.
15. `APPEAL_SUBMITTED`: Under appeal.
16. `APPEAL_UNDER_REVIEW`: Senior reviewing appeal.
17. `APPEAL_UPHELD`: Appeal won.
18. `APPEAL_DISMISSED`: Appeal lost.
19. `PAYMENT_PENDING`: Approved, awaiting batch.
20. `PAYMENT_PROCESSING`: IBG/DuitNow batch sent.
21. `PAID`: Funds cleared.
22. `CANCELLED`: Clinic withdrew.
23. `DUPLICATE_REJECTED`: Scrubber caught exact match.
24. `EXPIRED`: RAI timed out.
25. `FRAUD_CONFIRMED`: Final outcome of FWA investigation.

---

## SECTION 5 — APPEAL WORKFLOW (DEEP DIVE)
- **Who:** Initiated by Clinic or Patient within 30 days of EOB.
- **TPA SLA:** Acknowledgement in 3 working days. Final resolution in 14 working days (21 if Medical Advisor needed).
- **Process:** Senior Adjudicator handles. AI drafts suggested rebuttal based on new uploaded evidence.
- **Escalation:** If dismissed, system generates formal Final Rejection Letter displaying BNM LINK and OFS contact info (mandatory under BNM Fair Treatment guidelines).
- **Financial Impact:** If upheld, claim moves to `PAYMENT_PENDING` and a new EOB is issued superseding the denial.

---

## SECTION 6 — SYNTHETIC DATA SCENARIOS
1. **Clean Straight-Through (GP):** Patient visits panel GP for URTI (J06.9). RM 63.50. Passes scrubbing. Fraud score 0.08. Auto-approved.
2. **Denial for Pre-Existing (Specialist):** Patient on individual policy visits specialist for Diabetes (E11.9). Policy is 2 months old. System flags pre-existing condition. RAI confirms condition predates policy. `DENIED` (PRE_EXIST).
3. **Denial for Non-Panel Provider:** Patient visits non-panel clinic for Gastroenteritis. Employer scheme excludes non-panel outpatient. `DENIED` (NON_PANEL).
4. **Fraud Flag (Duplicate):** Clinic accidentally double-submits same claim. Confidence 0.97. Second claim is `DUPLICATE_REJECTED` automatically without manual review.
5. **Fraud Flag (Unusual Billing):** Clinic shows 78% MC issuance rate and 43% URTI concentration. Provider flagged as high-risk. Future claims move to `PENDING_FRAUD_REVIEW`. TPA suspends provider and reports to PIAM.
6. **RAI Loop (Hospital):** RM 8,500 claim for MRI without GP referral. Processor raises RAI. Clinic responds with inadequate data. Second RAI raised. Clinic provides specialist justification. Senior Adjudicator consults Medical Advisor. `APPROVED`. (28 days elapsed).
7. **Partial Approval:** Hospital claim for Cholecystectomy. Room & Board exceeds policy sublimit by RM 100/night. Medication (Omeprazole) not on formulary. `PARTIAL_APPROVAL` issued. Patient pays RM 320 out of pocket to hospital.
8. **Appeal Initiated & Reversed:** Claim initially denied for excluded psychiatric coverage (Anxiety, F41.1). Clinic appeals, clarifying primary complaint was cardiac (R00.0) and anxiety was incidental. Senior Adjudicator upholds appeal. `APPEAL_UPHELD`.
9. **Corporate Panel Claim:** Dependent child visits GP for ear infection. RM 77. HR sees aggregate cost but no clinical data. `APPROVED`.
10. **Emergency Retroactive LOG:** Patient suffers myocardial infarction at 11:45 PM. Emergency admission bypasses PA requirement. Next day, hospital runs ClaimIQ eligibility and TPA issues retroactive LOG. After 21-day review for undeclared conditions, claim is `APPROVED` for RM 28,400.

---

## SECTION 7 — NOTIFICATION & COMMUNICATION LAYER
- **Channels:** In-Portal (primary for all), Email (formal letters, batch reports), SMS (patient updates), WhatsApp Business API (opt-in for urgent RAIs).
- **Triggers:** Claim submitted, RAI requested (with 50% and 80% deadline alerts), Appeal Decision, Payment Executed.
- **Formal Letters:** TPA-to-Clinic communications (Denials, EOBs) are generated as PDFs with TPA letterheads. These are legally binding documents.

---

## SECTION 8 — COMPLIANCE & AUDIT CONSIDERATIONS
- **PDPA (2024 Amendment):** Explicit consent tracking. Data minimisation (HR cannot see diagnoses). Mandatory Incident Response Plan for 72-hour breach reporting. Right of Access (DSAR) workflows.
- **Retention:** Medical claims, audit logs, and attached docs retained for 7 years (MOH and BNM guidelines). Fraud records 10 years.
- **Immutable Audit Logging:** Every state transition, login, and data export is logged with User ID, IP, Action, and Timestamp (UTC+8).
- **Cross-Border Transfer:** If ClaimIQ is hosted outside Malaysia, legal protections must be verified under PDPA.

---

## SECTION 9 — GAPS & OPEN QUESTIONS
- **Actual BNM regulatory requirements for TPA platforms:** Does ClaimIQ itself require any form of BNM registration as a critical service provider to licensed insurers?
- **LOG/PA digitisation:** The exact format of LOGs varies. Will ClaimIQ issue digital LOG tokens, or generate PDFs matching legacy fax workflows?
- **Coordination of Benefits (COB):** How will ClaimIQ handle claims where the patient has a corporate scheme *and* a personal medical card, splitting the liability?
- **MOH clinic registration verification:** Real-time API verification of clinic licenses is not currently provided by MOH. Verification must be handled manually during TPA onboarding.
- **Takaful-specific adjudication differences:** Shariah-compliance implications for denial grounds must be reviewed with a takaful compliance expert.
