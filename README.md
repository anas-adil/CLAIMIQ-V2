<div align="center">
  <img src="https://raw.githubusercontent.com/anas-adil/CLAIMIQ-V2/main/media__1777748604449.png" alt="ClaimIQ Logo" width="200" style="border-radius: 12px; margin-bottom: 20px;"/>
  <h1>ClaimIQ</h1>
  <p><strong>Deterministic Clinical Adjudication & Fraud Intelligence Platform</strong></p>
  <p><i>UMHackathon 2026 Submission • Built with Z.AI ILMU & MedGemma Vision</i></p>
</div>

---

## 🚀 Live Demo
**Production Environment (Vercel):** [https://tpa-blue.vercel.app](https://tpa-blue.vercel.app)
*(Demo credentials are pre-filled on the login screen!)*

## 📺 Pitching Video
**Watch our full pitching video here:** 
👉 **[Insert Pitching Video Link Here]**

---

## 🧠 The Problem & Our Solution
Malaysian Third-Party Administrators (TPAs) lose millions annually to **Fraud, Waste, and Abuse (FWA)**, primarily through manual claims processing that fails to detect subtle clinical contradictions (e.g., claiming expensive treatments for mild conditions, or billing phantom services).

**ClaimIQ** is a next-generation TPA platform designed to eliminate unsafe fallback behaviors and automate the clinical adjudication pipeline with **100% auditability**.

### 🌟 Core Features:
1. **Multi-Modal Evidence Parsing ("MedGemma")**: Utilizes Vision Agents to extract structured data from complex, unstructured Malaysian medical documents (X-rays, Lab Reports, handwritten Invoices).
2. **"Double-Agent" Architecture**: Separates Vision Extraction (MedGemma) from Reasoning Adjudication (Z.AI ILMU) for maximum reliability and to prevent AI hallucinations.
3. **Cross-Reference Fraud Engine**: Deterministically compares Doctor's Notes vs. Lab Results to flag identity mismatches and clinical contradictions (e.g., "Doctor claims severe dengue, but Lab Report shows normal platelets").
4. **Safety-First Design**: An automated "Safety Freeze" prevents autonomous denials. All negative outcomes are gated for human clinical sign-off, ensuring 100% regulatory compliance.
5. **Immutable Audit Trail**: Every decision state change and AI reasoning step is logged deterministically.

---

## ⚡ Key Critical Component: Z.AI ILMU Integration
**ClaimIQ is powered primarily by Z.AI’s ILMU `nemo-super` Architecture.** 

As per the competition requirements, Z.AI serves as the central brain and main critical component of our solution. We utilize it for:
* **Clinical Adjudication**: Processing extracted clinical data against complex medical policies and RAG-based insurance rules.
* **Medical Coding**: Mapping doctor descriptions to standard ICD-10 and CPT codes automatically.
* **Fraud & Anomaly Detection**: Identifying sophisticated fraud patterns like Upcoding and Phantom Billing.
* **GP Advisory**: Generating human-readable, professional guidance (in English & Bahasa Malaysia) for clinics to improve documentation.

---

## 🛠 Technical Architecture
ClaimIQ operates on a sophisticated, serverless-ready 3-layer architecture:
1. **Ingestion & Triage**: Validating image quality and identifying document types.
2. **Evidence Extraction**: Converting unstructured images into structured JSON medical data.
3. **Intelligence Layer**: Adjudicating against benefit tiers, cross-referencing evidence, and generating risk scores.

### Tech Stack
* **Backend**: Python 3.10, FastAPI, SQLite (ephemeral `/tmp` storage for Vercel Serverless compatibility)
* **Frontend**: Vanilla JS, HTML5, CSS3 (Glassmorphism & Dynamic Dashboards)
* **AI Models**: Z.AI ILMU (`nemo-super`), Google Gemini (Vision)
* **Deployment**: Vercel CI/CD

---

## 📂 Project Structure
* `execution/`: Core backend logic and Frontend portal.
  * `api_server.py`: FastAPI serverless endpoints.
  * `claims_processor.py`: The deterministic adjudication pipeline.
  * `glm_client.py`: Core AI integration and prompt engineering.
  * `frontend/`: The stunning UI dashboards.
* `docs/`: Competition deliverables (PRD, SAD, TAD, QATD, Pitch Deck).

---

## 🏁 Getting Started (Local Development)

### Prerequisites
* Python 3.10+
* Z.AI ILMU API Key
* Gemini API Key

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/anas-adil/CLAIMIQ-V2.git
   cd CLAIMIQ-V2
   ```
2. Install dependencies:
   ```bash
   pip install fastapi uvicorn openai google-generativeai pydantic python-multipart
   ```
3. Set up your `.env` file (see `.env.example` for required keys):
   ```env
   GEMINI_API_KEY=your_key
   ILMU_API_KEY=your_key
   ILMU_BASE_URL=https://ilmu.zai.example/v1
   ILMU_MODEL=nemo-super
   ```
4. Run the server:
   ```bash
   cd execution
   python api_server.py
   ```
5. Open `http://localhost:8000` in your browser.

---

## ☁️ Deployment (Vercel)
This repository is configured for seamless deployment to Vercel via the `vercel.json` and `.vercel` configurations. 

1. Connect this GitHub repository to your Vercel Dashboard.
2. Ensure you add the API Keys (`GEMINI_API_KEY`, `ILMU_API_KEY`, etc.) to the **Environment Variables** section in your Vercel Project Settings.
3. Deploy! The system is configured to safely route SQLite databases to `/tmp` to support Vercel's read-only serverless filesystem.

---

## 📄 Documentation
The following mandatory files are available in the repository:
1. **Business Proposal** (`ClaimIQ_Business_Proposal.md`)
2. **QATD** (Quality Assurance Testing Document)
3. **PRD** (Product Requirements Document)
4. **SAD** (Software Architecture Document)
5. **TAD** (Technical Architecture Document)

---
*© 2026 ClaimIQ Team | Developed for the UMHackathon 2026 Submission.*
