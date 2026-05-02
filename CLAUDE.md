# ClaimIQ: Implementation Status and Technical Reference (May 2, 2026)

## Overview
ClaimIQ is a FastAPI + Vanilla JS claims intelligence platform for Malaysian TPA workflows. It supports claim intake, deterministic validation, policy-grade disposition gating, AI-assisted adjudication, fraud scoring, eligibility checks, auditability, analytics, and GP-facing advisory outputs.

This document reflects the current repository implementation, including recent backend and frontend upgrades.

## Current Local URLs
- App UI: `http://127.0.0.1:8000`
- API Health: `http://127.0.0.1:8000/api/health`
- API Docs: `http://127.0.0.1:8000/docs`

## Core Architecture
- Backend: FastAPI (`execution/api_server.py`)
- Pipeline Orchestration: `execution/claims_processor.py`
- Persistence: SQLite with migrations (`execution/database.py`)
- LLM Client: GLM-compatible OpenAI client wrapper (`execution/glm_client.py`)
- Policy Retrieval: FAISS + embedding retrieval (`execution/rag_engine.py`)
- Frontend: static HTML/CSS/JS (`execution/frontend/*`)
- Deterministic validation: `execution/validation_engine.py`
- Deterministic disposition gates: `execution/disposition_engine.py`
- Cross-reference engine: `execution/cross_reference_engine.py`
- Runtime policy config: `execution/policy_config.json`

## Claim Processing Pipeline (Current)
1. Intake and record creation (`POST /api/claims/submit`)
2. Structured extraction from claim text (GLM)
3. Evidence parsing (invoice/lab attachments)
4. Deterministic cross-reference and consistency validation
5. Scrubbing checks
6. Eligibility verification
7. Deterministic disposition evaluation (hard-gate matrix)
8. If hard-gate finalizes: immediate status finalization (skip LLM adjudication)
9. Otherwise: clinical validation, coding, policy adjudication (with RAG)
10. Fraud scoring and graph enrichment
11. GP advisory generation
12. EOB generation and final status handling

## Deterministic Disposition Model (Phase 1)
Disposition classes:
- `REJECT_INVALID`
- `DENY_POLICY`
- `PEND_REVIEW`
- `APPROVE`

Policy-driven mapping is configured in `execution/policy_config.json`:
- `identity_mismatch_action`
- `timely_filing_action`
- `missing_parse_with_attachment_action`
- `status_map`
- `appealability`
- `timely_filing_days`
- rule metadata and `policy_version`

Current status mapping:
- `REJECT_INVALID` -> `DENIED`
- `DENY_POLICY` -> `DENIED`
- `PEND_REVIEW` -> `UNDER_REVIEW`
- `APPROVE` -> `APPROVED`

Hard-gate rules implemented in `disposition_engine.py`:
- `ID_MATCH_001`: identity mismatch across claim and evidence
- `TF_LIMIT_001`: timely filing exceeded
- `PARSE_001`: attachment declared but parse unavailable
- `ELIG_001`: deterministic eligibility failure path

When `finalize_now=true`, the system writes a final deterministic decision immediately and does not rely on LLM adjudication for outcome selection.

## Status and Review Behavior
- Uses lifecycle/status fields in `claims` table.
- Legacy/manual review endpoints still set `UNDER_REVIEW` for appeal/RAI/fraud-clear workflows.
- Deterministic hard-gate outcomes now take priority during processing runs.

## Implemented Feature Upgrades

### 1) Evidence Consistency Validation
- `validation_engine.py` compares claim vs parsed evidence for:
  - identity (name/IC)
  - dates
  - amount consistency
- Outputs structured findings:
  - `severity`
  - `type`
  - `field`
  - `claim_value`
  - `evidence_value`
  - `source_doc`
  - `evidence_id`
  - `note`

### 2) Cross-Reference Contradiction Detection
- `cross_reference_engine.py` returns:
  - `verdict`
  - `checks[]`
  - `contradiction_count`
  - `critical_count`
  - `validation_findings[]`
  - `deterministic_summary`
- Critical contradictions can trigger fraud-risk escalation and deterministic gating.

### 3) Deterministic Disposition Orchestration
- `claims_processor.py` evaluates disposition before LLM adjudication.
- If triggered, writes decision with:
  - `disposition_class`
  - `rule_hits`
  - `policy_version`
  - `appealable`
- Final claim status is set immediately from policy mapping.

### 4) Prompt Hardening for Adjudication
- Adjudication prompt now receives deterministic findings and constraints.
- LLM is instructed not to contradict deterministic rule outputs.
- LLM remains responsible for reasoning/advisory language when not hard-gated.

### 5) UI Decision Transparency
- Claim modal includes:
  - Evidence Consistency card
  - Decision Basis details in adjudication card
  - Rule hits, disposition class, policy version, appealability (when present)

### 6) Token Metrics Dashboard
- GLM token usage is accumulated in `glm_client`.
- Endpoint: `GET /api/metrics`
- Dashboard card displays total tokens.

### 7) Denial Predictor (Synthetic ML)
- Module: `execution/denial_predictor.py`
- Model: RandomForest trained on synthetic vectors.
- Pipeline injects `denial_prediction` into decision payload.
- Claim modal shows denial probability and risk level.

### 8) Fraud Graph Signal
- Module: `execution/fraud_graph.py` (NetworkX)
- Provider-patient graph signal influences fraud score multiplier.
- Pipeline stores graph signal in fraud result.

### 9) PDPA Audit Extensions + Export
- Audit log schema includes PDPA-oriented fields:
  - `data_classification`
  - `retention_period`
  - `data_minimization_applied`
  - `consent_basis`
  - `cross_border_transfer`
- Endpoint: `GET /api/claims/{claim_id}/export`

### 10) Co-pay Engine
- Module: `execution/copay_engine.py`
- Eligibility integrates computed co-pay and rule label.
- EOB uses eligibility financial outputs.

### 11) FHIR Eligibility Mock
- Endpoint: `POST /api/fhir/coverage-eligibility`
- Endpoint: `POST /fhir/Patient/{ic_number}/$coverage-eligibility`
- Returns FHIR-like `EligibilityResponse` structure.

### 12) DRG Readiness Mapping
- Module: `execution/drg_mapper.py`
- ICD -> DRG lookup available.
- Claim modal shows DRG readiness badge text.

### 13) Safety Gate UI and Review Flow
- Modal surfaces review controls for pending statuses.
- Endpoint: `POST /api/claims/{claim_id}/review`
- Action body supports `APPROVE` or `DENY`.

### 14) MC Behavioral Analytics
- Module: `execution/mc_analytics.py`
- Endpoint: `GET /api/analytics/mc-patterns`
- Analytics view renders weekday distribution chart.

### 15) Bilingual EOB PDF
- Endpoint: `GET /api/claims/{claim_id}/eob.pdf`
- PDF generated by `reportlab` in `execution/eob_generator.py`.

### 16) Evidence Persistence During Processing
- Submit pipeline stores evidence attachment payload in `extracted_data`.
- Processor preserves `_evidence_base64` and `_invoice_base64` fields during extraction updates.
- This ensures reprocessing can still parse and validate attachments.

## Frontend Visibility Notes
Some features are conditional and appear only when matching data exists:
- Explainability citations appear only if decision contains `reasoning_citations`.
- Denial predictor appears only on claims processed through current pipeline.
- Evidence Consistency and Decision Basis appear when cross-ref/disposition payloads exist.
- Safety review controls appear only for `PENDING_APPROVAL` / `PENDING_DENIAL`.
- EOB PDF button appears only when EOB exists for claim.

## Key API Endpoints (active)
### Claims
- `POST /api/claims/submit`
- `POST /api/claims/process/{claim_id}`
- `GET /api/claims/{claim_id}`
- `GET /api/claims/`
- `POST /api/claims/{claim_id}/appeal`
- `POST /api/claims/{claim_id}/chat`
- `POST /api/claims/{claim_id}/review`
- `GET /api/claims/{claim_id}/export`
- `GET /api/claims/{claim_id}/eob.pdf`

### Analytics and Metrics
- `GET /api/analytics/summary`
- `GET /api/analytics/kpis`
- `GET /api/analytics/clinics`
- `GET /api/analytics/denials`
- `GET /api/analytics/fraud-heatmap`
- `GET /api/analytics/mc-patterns`
- `GET /api/metrics`

### Interoperability
- `POST /api/fhir/coverage-eligibility`
- `POST /fhir/Patient/{ic_number}/$coverage-eligibility`

### Demo
- `POST /api/demo/seed`
- `POST /api/demo/generate`

## Testing Status
Current local tests include scrubber, EOB, fraud, API endpoint coverage, and deterministic rule modules.
- Run: `pytest -q tests`
- Deterministic modules:
  - `tests/test_validation_engine.py`
  - `tests/test_disposition_engine.py`

## Environment Variables (commonly used)
- `ILMU_API_KEY` or `ZAI_API_KEY`
- `ILMU_BASE_URL` or `ZAI_BASE_URL`
- `ILMU_MODEL` or `ZAI_MODEL`
- `DB_PATH`
- `ALLOWED_ORIGINS`
- `APP_ENV`
- `API_PORT`
- Optional auth: `API_BEARER_TOKEN`

## Operational Notes
- If UI appears empty, verify backend is running at `127.0.0.1:8000`.
- Use demo seeding for immediate data population.
- Browser hard refresh is recommended after frontend version updates.
- Database path defaults to `.tmp/claimiq.db` unless `DB_PATH` is set.
- Reprocessing older claims is recommended after major policy-gate changes so legacy decisions are replaced by current deterministic outcomes.
