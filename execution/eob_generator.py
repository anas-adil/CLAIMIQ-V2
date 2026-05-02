"""
eob_generator.py — Structured EOB generation

Generates an Explanation of Benefits (EOB) document representation
based on adjudication results and member eligibility.
"""

import sys, os, json, logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import database as db
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

logger = logging.getLogger("claimiq.eob")

def generate_eob(claim_id: int, claim_data: dict, adjudication: dict, eligibility: dict) -> dict:
    """Generate structured EOB using adjudication plus eligibility financials."""
    total_billed = claim_data.get("total_amount_myr", 0) or 0
    decision = adjudication.get("decision", "DENIED")
    copay = eligibility.get("copay_myr", 0) or 0
    covered_by_elig = eligibility.get("covered_amount_myr", 0) or 0
    
    if decision in ("APPROVED", "PENDING_APPROVAL"):
        covered = covered_by_elig if covered_by_elig > 0 else (adjudication.get("amount_approved_myr", 0) or 0)
        patient_resp = max(0, total_billed - covered + copay)
        denial_code = None
        denial_desc = None
        eob_text = f"Claim for RM {total_billed:.2f} approved. Plan covers RM {covered:.2f}. Patient responsibility: RM {patient_resp:.2f}."
        eob_text_bm = f"Tuntutan sebanyak RM {total_billed:.2f} diluluskan. Pelan menanggung RM {covered:.2f}. Tanggungjawab pesakit: RM {patient_resp:.2f}."
    else:
        covered = 0
        patient_resp = max(0, total_billed + copay)
        denial_code = adjudication.get("denial_reason_code", "4")
        denial_desc = adjudication.get("denial_reason_description", "The service/drug/supply is not covered")
        eob_text = f"Claim for RM {total_billed:.2f} denied. Reason code {denial_code}: {denial_desc}. Patient responsibility: RM {patient_resp:.2f}."
        eob_text_bm = f"Tuntutan sebanyak RM {total_billed:.2f} ditolak. Kod sebab {denial_code}: {denial_desc}. Tanggungjawab pesakit: RM {patient_resp:.2f}."

    result = {
        "billed_amount_myr": total_billed,
        "covered_amount_myr": covered,
        "patient_responsibility_myr": patient_resp,
        "denial_code": denial_code,
        "denial_description": denial_desc,
        "eob_text": eob_text,
        "eob_text_bm": eob_text_bm,
    }
    
    db.insert_eob(claim_id, result)
    return result


def build_eob_pdf_bytes(claim: dict) -> bytes:
    eob = claim.get("eob") or {}
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "ClaimIQ - Explanation of Benefits")
    y -= 28
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Claim ID: {claim.get('id')}")
    y -= 16
    c.drawString(40, y, f"Member: {claim.get('patient_name') or 'N/A'}")
    y -= 16
    c.drawString(40, y, f"Diagnosis: {claim.get('diagnosis') or 'N/A'}")
    y -= 22
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Decision: {claim.get('status')}")
    y -= 24
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Billed Amount (MYR): {eob.get('billed_amount_myr', 0):.2f}")
    y -= 16
    c.drawString(40, y, f"Covered Amount (MYR): {eob.get('covered_amount_myr', 0):.2f}")
    y -= 16
    c.drawString(40, y, f"Patient Responsibility (MYR): {eob.get('patient_responsibility_myr', 0):.2f}")
    y -= 20
    if eob.get("denial_code"):
        c.drawString(40, y, f"Denial Code: {eob.get('denial_code')} - {eob.get('denial_description')}")
        y -= 20
    c.setFont("Helvetica", 9)
    c.drawString(40, y, "EN: " + (eob.get("eob_text") or ""))
    y -= 14
    c.drawString(40, y, "BM: " + (eob.get("eob_text_bm") or ""))
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
