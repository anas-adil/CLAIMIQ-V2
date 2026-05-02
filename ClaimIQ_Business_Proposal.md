# BUSINESS PROPOSAL
## ClaimIQ — AI-Powered Claims Intelligence Platform
### UMHackathon 2026

---

## 1. Executive Summary

Malaysia's private healthcare system is under severe financial stress. In 2024, medical claims inflation reached **21.6%** while insurance premiums grew only **13.2%**, creating a structural funding gap that is forcing double-digit premium hikes on millions of policyholders (Galen Centre, 2024; World Bank, 2026). At the centre of this crisis sits the claims processing pipeline: a fragmented, largely manual system relying on panel clinics, Third-Party Administrators (TPAs), and paper-based adjudication workflows that are slow, fraud-prone, and opaque.

**ClaimIQ** is a next-generation AI-powered TPA platform that automates the entire outpatient claims lifecycle—from clinical document ingestion to final adjudication decision—in under 90 seconds. Built on a multi-modal "Double-Agent" architecture combining vision AI (document parsing) and a Large Language Model reasoning engine (GLM-powered adjudication), ClaimIQ delivers deterministic, auditable, and regulation-compliant claims decisions at a fraction of today's manual cost.

Our two flagship innovations directly address Malaysia's most urgent regulatory and operational pressures:

1. **BNM-Compliant Tiered Co-Pay Engine** — Automatically calculates and enforces the Bank Negara Malaysia (BNM) mandated co-payment structure (effective 1 September 2024), applying the correct 5%-or-RM500 rule with all statutory exemptions (emergency, cancer, government facilities) computed in real time at the point of adjudication.

2. **MC Analytics & Abuse Detection Engine** — Identifies "MC Mill" clinics and habitual sick-leave abusers by analysing Medical Certificate (MC) issuance patterns against ICD-10 diagnosis codes, weekday distribution, and patient-visit frequency—generating HR-ready alerts without violating the Employment Act 1955.

ClaimIQ serves three customer segments: **panel clinics** (faster payment, AI-assisted coding), **corporate employers / insurers** (cost containment, fraud reduction), and **TPAs** (straight-through processing, regulatory compliance). Our SaaS model targets RM 2.4 M ARR within 24 months of launch.

---

## 2. Product Overview / Solution

### 2.1 Key Features

**A. 8-Step Autonomous Adjudication Pipeline**
Every submitted claim flows through a sequential AI pipeline:
1. Document Triage — image quality validation, document type classification
2. Multi-Modal Evidence Extraction — Vision AI parses X-rays, lab reports, and invoices into structured JSON
3. Medical Coding — ICD-10 and CPT code assignment via GLM reasoning
4. Eligibility Scrubbing — panel membership, policy coverage, filing deadline validation
5. Clinical Cross-Reference — AI compares doctor's notes against objective lab/imaging findings to detect contradictions
6. Policy Adjudication (RAG) — FAISS-indexed policy documents provide context for GLM-based approval/denial decision
7. Fraud Scoring — 7-pattern detection engine (phantom billing, upcoding, impossible timing, duplicate claims, etc.)
8. GP Advisory Generation — plain-language Bahasa Malaysia and English decision explanation for the clinic

**B. BNM Tiered Co-Pay Engine (Flagship)**
Fully implements the BNM September 2024 co-payment mandate:
- Applies 5% of claimable amount or RM 500 minimum deductible, whichever applies
- Automatically exempts: trauma/accident cases (ICD S/T codes), oncology/dialysis follow-ups (ICD C codes), government facility visits
- Co-pay amount is computed at adjudication and surfaced on the Explanation of Benefits (EOB) for both clinic and employer
- Enables insurers to offer co-payment products up to **68% cheaper** in premiums (BNM, 2024)

**C. MC Analytics & Abuse Intelligence (Flagship)**
A first-of-its-kind MC behaviour intelligence layer:
- Tracks Monday/Friday MC clustering by patient IC and clinic
- Flags "MC Mill" clinics where >80% of minor illness visits (J06.9 URTI, K29.7 Gastritis, R51 Headache) result in an MC
- Calculates per-patient and per-clinic MC Risk Scores (0.0–1.0)
- Generates HR alerts for employers without illegally altering payment (Employment Act 1955 compliant)
- Provides analytics dashboard: weekday distribution heatmap, frequent-patient leaderboard, same-day clinic spike alerts

**D. Safety-First "Doctor-First" Architecture**
- All negative decisions (denials) are gated through a human TPA Processor review ("Safety Freeze")
- Every AI decision is logged with SHA-256 integrity hashes for immutable audit trails
- Full PDPA 2024 compliance: data minimisation, purpose limitation, audit log retention

**E. Role-Based Multi-Portal System**
- **Clinic Portal**: Submit claims, track status, receive AI-coded advisory, file appeals
- **TPA Processor Portal**: Review queue, approve/deny/raise RAI, view AI reasoning
- **Fraud Analyst Portal**: Flagged claims dashboard, provider risk leaderboard, fraud network graph
- **System Admin Portal**: User management, seed demo data, view audit logs, token cost tracking

### 2.2 Technology Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.13, FastAPI, Uvicorn |
| AI Reasoning Engine | Z.AI GLM (GLM-4-Plus via OpenAI-compatible API) |
| Vision / Document AI | Google MedGemma, Gemini Vision |
| Vector RAG | FAISS (sentence-transformers, all-MiniLM-L6-v2) |
| Database | SQLite (production: PostgreSQL via Supabase) |
| Authentication | JWT HS256 (PyJWT), bcrypt password hashing |
| Frontend | Vanilla JS, CSS3 (glassmorphism dark UI), HTML5 |
| Fraud Graph | NetworkX |
| Deployment | Uvicorn ASGI, background thread processing |

---

## 3. Market Research & Market Dynamics

### 3.1 Problem Landscape

Malaysia's outpatient claims ecosystem suffers from four compounding structural failures:

**Problem 1 — The Claims Cost Crisis**
Malaysian medical claims surged **73% from 2022 to 2024** while premiums grew only **21%** (Galen Centre, 2024). Claims inflation hit **21.6% in 2024** — more than 8× the general CPI. The primary driver is not cost-per-treatment but **overutilisation** (contributing ~70% of cost growth), including unnecessary consultations, inflated billing, and widespread MC issuance abuse (World Bank, 2026).

**Problem 2 — Manual, Slow Adjudication**
The current TPA workflow is predominantly manual. A panel clinic submits a paper or scanned claim; a human processor at the TPA validates it against policy schedules. Average adjudication time is **3–7 days** for outpatient claims. Industry benchmarks show initial claim denial rates of **11–12%** — most due to correctable administrative errors (missing codes, wrong ICD) that AI can resolve at point of submission (MGMA, 2024).

**Problem 3 — Fraud, Waste & Abuse (FWA)**
Healthcare insurance FWA is a documented and growing problem in Malaysia. Notable 2024 cases: the Madani Medical Scheme fraud (false claims, medication sold without consultation) and the SOCSO cartel (millions siphoned via false disability claims). Industry observers describe widespread **"buffet table syndrome"** — over-utilisation encouraged by full-coverage plans — and systematic **upcoding** (submitting inflated diagnosis codes). No existing TPA platform applies real-time clinical cross-referencing to catch these patterns automatically.

**Problem 4 — BNM Regulatory Compliance Burden**
The BNM co-payment mandate (effective 1 September 2024) requires all insurers to offer products with a minimum 5% or RM 500 co-payment. This is a **new operational requirement** for every TPA system in Malaysia. Most legacy TPA platforms have no automated co-payment computation, forcing manual calculation and creating compliance risk and premium leakage.

### 3.2 Market Niche

ClaimIQ targets the underserved **outpatient TPA automation** segment of the Malaysian private healthcare market, specifically:

- **Primary**: Small-to-mid-size TPAs (MiCare, IHP, MediExpress tier) processing 500–5,000 outpatient claims/month, seeking to modernise without building AI capability in-house
- **Secondary**: Corporate HR / Employee Benefits teams at companies with 100–5,000 employees managing panel clinic programs who are losing money to MC abuse and overutilisation
- **Tertiary**: Panel clinics (GPs) seeking faster reimbursement, ICD coding assistance, and transparent dispute resolution

### 3.3 Market Sizing

| Market Layer | Size | Source |
|---|---|---|
| Malaysian Overall Healthcare Market | USD 27.87 B (2024) | Nexdigm / ResearchAndMarkets |
| Malaysian Hospital Sector | USD 11.52 B (2024) | MarketResearch.com |
| Private healthcare growth rate | +9.3% p.a. (2022–2024) | MIDF Research |
| AI for Healthcare Payer (Global) | USD 2.11 B (2024) → USD 7.15 B (2033) | Grand View Research |
| AI Claims Automation CAGR | 15.26% (2025–2033) | Grand View Research |
| Malaysia health insurance private spending | 17% of private healthcare financing | MNHA 2024 |

**Serviceable Addressable Market (Malaysia):**
Assuming ~1.5 million outpatient panel claims processed monthly by Malaysian TPAs, at an average processing cost of RM 15/claim (manual), the addressable cost pool is approximately **RM 270 M/year**. ClaimIQ's SaaS model captures value by reducing this per-claim cost to under RM 3 (AI-processed), while charging TPAs a platform fee of RM 5–8/claim.

**SAM (Malaysia, Outpatient TPA)**: RM 108 M/year  
**SOM (Year 3, 5% capture)**: RM 5.4 M ARR

### 3.4 Market Dynamics & Placement

**Regulatory Tailwind — BNM Co-Pay Mandate (September 2024)**
Every TPA operating in Malaysia must now compute co-payments correctly on every claim. ClaimIQ is the only platform with a purpose-built, statute-aware co-pay engine. This creates an immediate compliance-driven buying trigger.

**Medical Inflation Crisis → Cost-Containment Demand**
With premiums rising 13–21% annually, every corporate CFO and insurer is actively seeking cost containment tools. ClaimIQ's MC Analytics and fraud scoring directly address this demand with measurable, reportable savings.

**Digital Transformation Momentum**
Malaysian TPAs are actively shifting from paper-based to digital claims platforms. Major players (WeCare TPA, IHP) have launched apps but lack AI adjudication. ClaimIQ leapfrogs them with a full intelligence layer.

**PDPA 2024 Compliance Pressure**
The 2024 PDPA amendments impose stricter data handling requirements on healthcare processors. ClaimIQ's immutable audit trail and role-based access controls are designed for this compliance environment.

---

## 4. Value Proposition & Competitive Advantage

ClaimIQ redefines the economics of outpatient claims adjudication by replacing a 3–7 day human workflow with a <90 second AI pipeline while maintaining Doctor-First safety gates.

**For TPAs:**
- Reduce per-claim processing cost from ~RM 15 (manual) to ~RM 3 (AI-STP)
- Achieve Straight-Through Processing (STP) rates of 70–80% for clean claims
- Automatic BNM co-payment calculation eliminates compliance risk
- Immutable audit trail satisfies BNM and PDPA audit requirements

**For Corporate Employers / Insurers:**
- MC Analytics dashboard quantifies and identifies habitual MC abuse patterns
- Fraud scores flag high-risk clinics before payment, not after
- Real-time EOB (Explanation of Benefits) generation for every claim
- Projected 8–15% reduction in outpatient medical costs through fraud/abuse detection

**For Panel Clinics (GPs):**
- AI-suggested ICD-10/CPT codes reduce coding errors and denial rates
- Faster payment (STP claims paid within 24h vs. 3–7 days)
- Plain-language GP Advisory explains every decision and suggests documentation improvements
- Transparent appeal workflow with AI-drafted rebuttal letters

**Defensible Advantages:**
1. **Regulatory Specificity** — Co-pay engine built to Malaysian statute, not generic insurance rules
2. **Double-Agent AI Architecture** — Separates vision extraction from reasoning to prevent hallucination compounding
3. **MC Intelligence** — No competitor product in Malaysia specifically targets MC abuse pattern detection
4. **Safety-First Design** — "Doctor-First" freeze prevents the AI from autonomously denying claims without human oversight, addressing MMA concerns about TPA clinical overreach
5. **Full Auditability** — SHA-256 hashed audit logs satisfy PDPA, BNM, and MMA compliance simultaneously

---

## 5. Competitor Analysis (Porter's Five Forces)

### Competitive Landscape

| Dimension | Existing Malaysian TPAs | ClaimIQ |
|---|---|---|
| Adjudication Method | Manual / rule-based | AI + RAG + GLM reasoning |
| Co-Pay Computation | Manual / not automated | Automated, BNM-statute compliant |
| Fraud Detection | Post-payment audits | Real-time, clinical cross-reference |
| MC Abuse Monitoring | None / manual HR review | Automated pattern scoring dashboard |
| Decision Transparency | Opaque rejection letters | Full AI reasoning + GP advisory |
| Audit Trail | Paper/email records | SHA-256 immutable digital log |
| Processing Speed | 3–7 days | <90 seconds |

### Porter's Five Forces

**1. Threat of New Entrants — MEDIUM**
Building a compliant AI claims adjudication platform requires deep integration of healthcare regulation (BNM, MMA, PDPA, Employment Act), medical coding (ICD-10, CPT), and AI. The regulatory moat is significant. However, well-funded insurtech startups remain a future threat.

**2. Bargaining Power of Buyers — MEDIUM-HIGH**
Large TPAs and insurers have negotiating leverage on pricing. Mitigation: ClaimIQ's per-claim SaaS model aligns cost with value; switching costs are high once claims data and audit history are on-platform.

**3. Bargaining Power of Suppliers — LOW**
AI API costs are competitive (Z.AI GLM, Gemini). FAISS is open-source. No single supplier dependency.

**4. Threat of Substitutes — LOW-MEDIUM**
Manual processing is the current substitute — inefficient and expensive. Generic ERP systems cannot match ClaimIQ's medical-domain specificity.

**5. Competitive Rivalry — LOW (Currently)**
No Malaysian TPA platform currently offers real-time AI adjudication with BNM co-pay automation and MC abuse analytics. This is a first-mover window of 18–24 months before incumbents can respond.

---

## 6. Business Model Canvas

### 6.1 Customer Segments

**TPA Operators (Primary B2B)**
Mid-size TPAs processing 500–10,000 outpatient claims/month seeking to automate adjudication, reduce headcount cost, and achieve BNM compliance. Examples: MiCare, IHP, MediExpress tier operators.

**Corporate HR / Employee Benefits (Secondary B2B)**
Companies with 100–5,000 employees managing panel clinic medical benefits who face rising MC abuse, unexplained outpatient cost spikes, and lack of visibility into claims data.

**Panel Clinics / GP Practices (Tertiary)**
Private GP clinics seeking faster payment, ICD coding help, and lower administrative burden in submitting and tracking outpatient claims.

### 6.2 Revenue Streams

**Primary — Per-Claim SaaS Processing Fee**
- RM 5.00/claim for standard outpatient adjudication (AI STP)
- RM 8.00/claim for complex claims with multi-modal evidence (X-ray/lab parsing)
- Volume discounts: >2,000 claims/month → RM 4.00; >10,000 claims/month → RM 3.00

**Secondary — Platform Subscription (TPA Tier)**
- RM 1,500/month: Up to 500 claims, 3 user accounts, basic analytics
- RM 4,500/month: Up to 3,000 claims, unlimited users, MC Analytics dashboard, fraud leaderboard
- RM 12,000/month: Enterprise — unlimited claims, white-label portal, dedicated SLA, API access

**Tertiary — MC Analytics Reporting (HR Module)**
- RM 500/month add-on per corporate employer: monthly MC behaviour report, HR-ready alerts, clinic risk rankings

**Quaternary — API Access**
- RM 0.50/API call for insurers embedding ClaimIQ adjudication into their own systems

### 6.3 Cost Structure

| Cost Category | Year 1 (RM) | Year 2 (RM) |
|---|---|---|
| AI API Costs (GLM, Gemini) | 48,000 | 96,000 |
| Cloud Infrastructure | 24,000 | 48,000 |
| Engineering (2 FTE) | 180,000 | 240,000 |
| Sales & BD | 60,000 | 120,000 |
| Compliance & Legal | 30,000 | 36,000 |
| Operations | 24,000 | 36,000 |
| **Total** | **366,000** | **576,000** |

### 6.4 Key Partners

- **Z.AI / ILMU AI** — Core LLM reasoning engine (GLM-4-Plus)
- **Google** — MedGemma / Gemini Vision for medical document parsing
- **Panel Clinic Networks** — Distribution and data partnerships for onboarding
- **Malaysian Insurance & Takaful Association (LIAM/MTA)** — Industry compliance alignment
- **Bank Negara Malaysia** — Regulatory sandbox engagement for co-pay automation
- **Malaysian Medical Association (MMA)** — Clinical standards validation for AI adjudication

### 6.5 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AI model hallucination on clinical data | Medium | High | Double-Agent separation; Safety Freeze gate; human sign-off on all denials |
| BNM regulatory change | Low | High | Modular co-pay engine; statute references are parameterised, not hardcoded |
| TPA resistance to AI adjudication | Medium | Medium | Doctor-First architecture preserves clinical authority; AI = decision support, not replacement |
| Data breach / PDPA violation | Low | Critical | SHA-256 audit trail; role-based access; JWT session management; encrypted DB |
| GLM API downtime | Medium | High | Intelligent mock fallback; queue-based retry logic; auth-failure cooldown circuit breaker |
| MC false-positive alerts damaging clinic relationships | Low | Medium | Risk scoring surfaced as advisory only; not used to withhold payment |

---

## 7. Implementation & Financials

### 7.1 Go-to-Market Strategy

**Phase 1 — Hackathon Validation (Month 0–1)**
Deploy live demo at UMHackathon 2026. Demonstrate full end-to-end pipeline: document upload → AI adjudication → co-pay calculation → EOB output. Target 3 Letters of Intent from TPA or corporate HR attendees.

**Phase 2 — Pilot (Month 2–6)**
Partner with 1 mid-size TPA and 10–15 panel clinics for a paid pilot. Process 500–1,000 real outpatient claims with human oversight on all decisions. Measure: STP rate, fraud flag precision, processing time vs. baseline. Target: STP rate ≥65%, processing time <2 minutes, zero wrongful denials.

**Phase 3 — Commercial Launch (Month 7–12)**
Onboard 3 TPA clients and 50 panel clinics. Launch MC Analytics HR module to 5 corporate clients. Enable API access tier. Revenue target: RM 600K ARR by Month 12.

**Phase 4 — Scale (Month 13–24)**
Expand to Penang and Johor Bahru regional TPA operators. White-label offering for insurers. Launch Bahasa Malaysia full-interface for broader GP adoption. Revenue target: RM 2.4M ARR by Month 24.

### 7.2 Implementation Plan

| Milestone | Timeline | Deliverable |
|---|---|---|
| Hackathon MVP Complete | Month 0 | Full pipeline, 4-role portal, demo data |
| Pilot TPA Integration | Month 2 | API integration with 1 TPA's claims system |
| BNM Co-Pay Certification | Month 3 | Legal review of co-pay engine vs. BNM circular |
| MC Analytics Beta | Month 4 | HR dashboard live with 2 corporate clients |
| SOC 2 / PDPA Audit | Month 6 | External compliance audit completed |
| Commercial Launch | Month 7 | 3 TPA clients live, billing active |
| White-Label API | Month 12 | First insurer API client live |
| Series A Fundraise | Month 18 | RM 5M target for ASEAN expansion |

### 7.3 Revenue Projections (3-Year)

| Metric | Year 1 | Year 2 | Year 3 |
|---|---|---|---|
| TPA Clients | 3 | 8 | 18 |
| Claims Processed / Month | 5,000 | 20,000 | 60,000 |
| Avg Revenue / Claim | RM 5.50 | RM 5.00 | RM 4.50 |
| Claim Processing Revenue | RM 330K | RM 1.2M | RM 3.24M |
| Platform Subscriptions | RM 162K | RM 540K | RM 1.08M |
| MC Analytics Module | RM 60K | RM 180K | RM 480K |
| **Total Revenue** | **RM 552K** | **RM 1.92M** | **RM 4.8M** |
| **Total Costs** | **RM 366K** | **RM 576K** | **RM 840K** |
| **EBITDA** | **RM 186K** | **RM 1.34M** | **RM 3.96M** |
| **EBITDA Margin** | 34% | 70% | 82% |

### 7.4 Key Financial Milestones

- **Month 3**: First paying TPA client live. RM 13,500/month recurring.
- **Month 6**: Break-even on monthly operating costs. 3 TPA clients, 5,000 claims/month.
- **Month 12**: RM 600K ARR. MC Analytics module generating RM 5K/month.
- **Month 18**: RM 1.5M ARR. First white-label API contract signed.
- **Month 24**: RM 2.4M ARR. Cash-flow positive. ASEAN expansion feasibility review.
- **Month 30**: RM 3.6M ARR. Series A deployment into Singapore / Indonesia TPA markets.

---

## 8. Regulatory Compliance Summary

| Regulation | ClaimIQ Implementation |
|---|---|
| BNM Medical Insurance Co-Payment Circular (Sept 2024) | Purpose-built co-pay engine; 5%/RM500 rule; all statutory exemptions automated |
| Personal Data Protection Act (PDPA) 2024 | SHA-256 audit logs; role-based access; data minimisation; encrypted storage |
| Employment Act 1955 (MC provisions) | MC Analytics generates alerts only; does not alter payment or deny leave |
| Malaysian Medical Association Standards | Doctor-First Safety Freeze; AI is decision-support only; all denials require human sign-off |
| Companies Act 2016 (financial records) | Immutable EOB records; token cost tracking; full financial audit trail |

---

## 9. Conclusion

Malaysia's healthcare claims crisis is structural, urgent, and accelerating. The 2024 BNM co-payment mandate, surging medical inflation at 21.6%, and a documented fraud epidemic have created a market that actively needs what ClaimIQ delivers: fast, fair, auditable, and regulation-native AI adjudication.

ClaimIQ is not a generic AI wrapper. It is a purpose-built Malaysian TPA intelligence platform with two flagship innovations — the **BNM-Compliant Tiered Co-Pay Engine** and the **MC Abuse Analytics Module** — that no existing competitor in the Malaysian market currently offers.

The technology is built and live. The regulatory case is proven. The market is ready.

**ClaimIQ — Processing Claims at the Speed of Intelligence.**

---

*© 2026 ClaimIQ Team | Built for UMHackathon 2026 Final Round*

*Sources: Bank Negara Malaysia (2024), Galen Centre for Health & Social Policy (2024), World Bank Malaysia Health Expenditure Report (2026), Grand View Research AI Healthcare Payer Market (2024), Malaysian National Health Accounts (MNHA) 2024, MIDF Research Private Healthcare Sector Report (2024), Malaysian Medical Association, Employment Act 1955, PDPA Malaysia 2024.*
