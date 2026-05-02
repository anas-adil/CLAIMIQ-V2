from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import os

def generate_system_overview_pdf():
    doc_path = os.path.join("docs", "ClaimIQ_Technical_Overview.pdf")
    os.makedirs("docs", exist_ok=True)
    
    doc = SimpleDocTemplate(doc_path, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Custom styles
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        textColor=colors.HexColor("#1a73e8")
    )
    
    subhead_style = ParagraphStyle(
        'SubHeadStyle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#202124")
    )
    
    story = []
    
    # Title Page
    story.append(Paragraph("ClaimIQ: Technical System Overview", styles['Title']))
    story.append(Paragraph("Production-Grade Clinical Adjudication & Fraud Intelligence", styles['Heading2']))
    story.append(Spacer(1, 24))
    story.append(Paragraph("<b>Version:</b> 2.1 (Cloud-Native)", styles['Normal']))
    story.append(Paragraph("<b>Status:</b> Competition Ready", styles['Normal']))
    story.append(Spacer(1, 48))
    
    # 1. Main Critical Component (ilmu ai GLM)
    story.append(Paragraph("1. Main Critical Component: ilmu ai GLM", header_style))
    story.append(Paragraph(
        "ClaimIQ follows a <b>'Double-Agent' Architecture</b>. In this paradigm, we separate the 'Eyes' (Extraction) from the 'Brain' (Reasoning).",
        styles['Normal']
    ))
    story.append(Spacer(1, 12))
    
    data = [
        ['Component', 'API / Provider', 'Criticality', 'Function'],
        ['Vision Agent', 'Gemini Vision', 'Utility', 'OCR & Data Extraction from Images'],
        ['Adjudication Agent', 'ilmu ai GLM', 'CRITICAL', 'Medical Reasoning & Adjudication']
    ]
    t = Table(data, colWidths=[100, 120, 80, 200])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f3f4")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<b>Why Z.AI GLM is the core:</b> While Gemini is used for basic OCR, the Z.AI GLM Architecture is responsible for every medical decision made by the system. It cross-references patient benefits, validates clinical consistency, detects medical fraud, and generates final EOBs. Without Z.AI, the system has eyes but no intelligence.",
        styles['Normal']
    ))
    
    # 2. System Workflow
    story.append(Paragraph("2. System Workflow", header_style))
    story.append(Paragraph("The system implements a strictly deterministic 10-state lifecycle:", styles['Normal']))
    steps = [
        "1. <b>INTAKE:</b> Claim received via API/Frontend.",
        "2. <b>SCRUBBING:</b> Pre-validation check for data integrity.",
        "3. <b>ELIGIBILITY:</b> Verifying member coverage via Registry API.",
        "4. <b>PROCESSING:</b> Multi-modal analysis via Vision + GLM Adjudication.",
        "5. <b>ADJUDICATION:</b> Final score generated (Approve/Deny/Refer).",
        "6. <b>SAFETY FREEZE:</b> Any non-approved claim is gated for manual human review."
    ]
    for step in steps:
        story.append(Paragraph(step, styles['Normal']))
        story.append(Spacer(1, 6))
        
    # 3. Application Components
    story.append(PageBreak())
    story.append(Paragraph("3. Application Components", header_style))
    
    comp_data = [
        ['File', 'Responsibility'],
        ['api_server.py', 'FastAPI backend orchestrating routes and static frontend serving.'],
        ['database.py', 'Cloud persistence (Supabase) and Immutable Audit Logs.'],
        ['claims_processor.py', 'Core workflow engine handling state transitions.'],
        ['vision_agent.py', 'Wrapper for Gemini Vision API (Multi-modal Agent).'],
        ['adjudication_agent.py', 'Interface for ilmu ai GLM (Reasoning Agent).'],
        ['rag_engine.py', 'Retrieval Augmented Generation for medical policies.']
    ]
    t2 = Table(comp_data, colWidths=[120, 380])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f3f4")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t2)
    
    # 4. Frontend Navigation
    story.append(Paragraph("4. Frontend Navigation", header_style))
    pages = [
        "<b>Dashboard:</b> Centralized KPI tracking (Denial Rates, Auto-Adj Rate, AR Days).",
        "<b>Claims Grid:</b> Real-time view of claim statuses with filtering.",
        "<b>Clinical Detail View:</b> Deep-dive into AI reasoning, OCR results, and Fraud scores.",
        "<b>GP Advisory:</b> Portal for clinics to view automated guidance in multiple languages.",
        "<b>Settings:</b> Environment configuration and API health checks."
    ]
    for p in pages:
        story.append(Paragraph(f"• {p}", styles['Normal']))
        story.append(Spacer(1, 4))
        
    # 5. Deployment & Integration
    story.append(Paragraph("5. Deployment & Integration", header_style))
    story.append(Paragraph(
        "ClaimIQ is cloud-ready. It uses <b>Supabase</b> for persistent PostgreSQL storage and <b>Gemini/Z.AI</b> for intelligence. It can be deployed to Render or Railway with a single click by connecting the GitHub repository.",
        styles['Normal']
    ))
    
    doc.build(story)
    return doc_path

if __name__ == "__main__":
    path = generate_system_overview_pdf()
    print(f"PDF Generated at: {path}")
