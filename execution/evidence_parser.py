"""
evidence_parser.py — Main Evidence Parsing Orchestrator
"""

import logging
import document_triage
import medgemma_client

logger = logging.getLogger("claimiq.parser")

def parse_evidence(image_b64: str) -> dict:
    """
    Full evidence parsing pipeline.
    Returns: {
        "triage": {...},          # from document_triage
        "parsed_evidence": {...}, # from MedGemma
        "source": "MEDGEMMA_LIVE" | "PARSE_FAILED" | "NO_EVIDENCE",
        "parsing_confidence": 0.0-1.0
    }
    """
    if not image_b64:
        return {"source": "NO_EVIDENCE", "parsing_confidence": 1.0}
        
    logger.info("Triaging evidence document...")
    triage = document_triage.triage_evidence(image_b64)
    logger.info(f"Triage result: {triage['doc_type']} (Quality: {triage['quality']})")
    
    doc_type = triage["doc_type"]
    
    if triage["quality"] in ["POOR", "BLURRY", "SUSPECT"]:
        logger.warning(f"Parsing suboptimal image: {triage['warnings']}")
        
    logger.info(f"Routing to MedGemma parser for {doc_type}...")
    
    analyzer_order = {
        "XRAY": [medgemma_client.analyze_xray, medgemma_client.analyze_lab_report, medgemma_client.analyze_invoice],
        "LAB_REPORT": [medgemma_client.analyze_lab_report, medgemma_client.analyze_invoice, medgemma_client.analyze_xray],
        "INVOICE": [medgemma_client.analyze_invoice, medgemma_client.analyze_lab_report, medgemma_client.analyze_xray],
        "UNKNOWN": [medgemma_client.analyze_lab_report, medgemma_client.analyze_invoice, medgemma_client.analyze_xray],
    }
    parsed = None
    last_error = None
    for analyzer in analyzer_order.get(doc_type, analyzer_order["UNKNOWN"]):
        candidate = analyzer(image_b64)
        if "error" not in candidate:
            parsed = candidate
            break
        last_error = candidate.get("error", "")
        # Short-circuit: quota exhaustion affects all models equally — no point retrying
        if "quota_exhausted" in str(last_error) or "quota" in str(last_error).lower():
            logger.warning(f"Gemini quota exhausted — skipping fallback analyzers")
            break
        logger.warning(f"Evidence parser fallback attempt failed: {last_error}")
    if parsed is None:
        parsed = {"error": last_error or "parse_failed"}
        
    if "error" in parsed:
        logger.error(f"Evidence parsing failed: {parsed['error']}")
        return {
            "triage": triage,
            "parsed_evidence": parsed,
            "source": "PARSE_FAILED",
            "parsing_confidence": 0.0
        }
        
    confidence_key = "confidence" if doc_type == "XRAY" else "extraction_confidence"
    conf = parsed.get(confidence_key, parsed.get("confidence", 0.0))
    
    return {
        "triage": triage,
        "parsed_evidence": parsed,
        "source": parsed.get("_source", "MEDGEMMA_LIVE"),
        "parsing_confidence": conf
    }
