"""
medgemma_client.py — MedGemma 1.5 4B API Bridge (Colab → Local)

Calls MedGemma running on Google Colab via ngrok tunnel.
Set MEDGEMMA_API_URL in .env to the ngrok public URL.

Usage:
    from medgemma_client import analyze_xray, analyze_lab_report, analyze_invoice, health_check
"""

import os
import json
import logging
import time
import base64
import re
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("claimiq.medgemma")

MEDGEMMA_URL = os.getenv("MEDGEMMA_API_URL", "").rstrip("/")
TIMEOUT_ANALYSIS = int(os.getenv("MEDGEMMA_TIMEOUT_SEC", "120"))
TIMEOUT_HEALTH   = 10
MAX_RETRIES      = 2
# How long to wait after a 429 quota error before retrying (seconds)
QUOTA_RETRY_WAIT = 30


# ── Prompts ────────────────────────────────────────────────────────────────

PROMPT_XRAY = (
    "You are a radiology observation assistant. "
    "Describe ONLY what you can objectively observe in this chest X-ray image. "
    "Do NOT diagnose — only report visible radiological findings. "
    "Output ONLY valid JSON (no markdown, no code blocks):\n"
    '{"findings": ["<finding 1>", "<finding 2>"], '
    '"impression": "<1-sentence summary of key observations>", '
    '"confidence": <0.0-1.0>, '
    '"limitations": "<what cannot be determined from this image alone>"}'
)

PROMPT_LAB = (
    "You are a medical data extraction assistant. "
    "Extract ALL laboratory test results from this lab report image. "
    "Output ONLY valid JSON (no markdown, no code blocks):\n"
    '{"patient_name_on_report": "<full name exactly as printed, or null>", '
    '"ic_number_on_report": "<IC/NRIC/passport number exactly as printed, or null>", '
    '"registered_date": "<registered or collected date or null>", '
    '"report_date": "<reported/printed date or null>", '
    '"facility": "<lab/clinic name or null>", '
    '"results": [{"test": "<test name>", "value": <numeric value>, '
    '"flag": "<L, H, or null>", "unit": "<unit>", "ref_range": "<low-high>"}], '
    '"extraction_confidence": <0.0-1.0>}'
)

PROMPT_INVOICE = (
    "You are a medical invoice extraction assistant. "
    "Extract ALL line items and totals from this medical invoice image. "
    "Output ONLY valid JSON (no markdown, no code blocks):\n"
    '{"facility": "<name or null>", "invoice_date": "<date or null>", '
    '"patient_name_on_invoice": "<full name exactly as printed, or null>", '
    '"ic_number_on_invoice": "<IC/NRIC/passport number exactly as printed, or null>", '
    '"items": [{"description": "<item>", "quantity": <num>, '
    '"unit_price": <num>, "total": <num>}], '
    '"grand_total": <total amount as number>, '
    '"extraction_confidence": <0.0-1.0>}'
)

PROMPT_CLASSIFY = (
    "Classify this medical document. "
    "Output ONLY valid JSON (no markdown, no code blocks):\n"
    '{"doc_type": "<XRAY|LAB_REPORT|INVOICE|UNKNOWN>", "confidence": <0.0-1.0>, '
    '"reasoning": "<1 sentence>"}'
)


# ── Internal helpers ────────────────────────────────────────────────────────

def _post(endpoint: str, payload: dict, timeout: int) -> dict:
    """Raw POST to MedGemma Colab API. Returns dict or raises."""
    url = f"{MEDGEMMA_URL}{endpoint}"
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _is_pdf(raw_bytes: bytes) -> bool:
    return raw_bytes[:4] == b"%PDF"


def _analyze(image_b64: str, prompt: str, doc_type: str) -> dict:
    """
    Send an image or PDF + prompt to Gemini API. Returns structured result dict.
    Uses the new google-genai SDK (google.genai).
    """
    from google import genai as new_genai
    from google.genai import types as genai_types
    from PIL import Image
    from io import BytesIO

    # Strip data-URI prefix if present
    if image_b64 and image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[-1]

    gemini_key = os.getenv("gemini") or os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        logger.error("Gemini API key missing in .env (tried 'gemini' and 'GEMINI_API_KEY')")
        return {"error": "gemini_api_key_missing", "source": "GEMINI_LIVE"}

    # Model preference order: configured → 2.5-flash → 1.5-flash (fallback)
    primary_model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    model_order = [primary_model]
    for fallback in ["gemini-2.5-flash", "gemini-1.5-flash"]:
        if fallback not in model_order:
            model_order.append(fallback)

    client = new_genai.Client(api_key=gemini_key.strip())
    analysis_text = ""

    # Pre-decode bytes once
    raw_bytes = base64.b64decode(image_b64)
    if _is_pdf(raw_bytes):
        media_part = genai_types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf")
        logger.info(f"Gemini [{doc_type}]: PDF detected")
    else:
        image = Image.open(BytesIO(raw_bytes))
        buf = BytesIO()
        fmt = image.format or "PNG"
        image.save(buf, format=fmt)
        mime = f"image/{fmt.lower()}" if fmt.lower() in ("png","gif","webp") else "image/jpeg"
        media_part = genai_types.Part.from_bytes(data=buf.getvalue(), mime_type=mime)

    for model_name in model_order:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"Gemini [{doc_type}] model={model_name} attempt={attempt}/{MAX_RETRIES}")
                t0 = time.time()
                response = client.models.generate_content(
                    model=model_name,
                    contents=[media_part, prompt],
                )
                elapsed = time.time() - t0
                logger.info(f"Gemini [{doc_type}] OK in {elapsed:.1f}s model={model_name}")

                analysis_text = response.text or ""
                if not analysis_text:
                    return {"error": "empty_response", "source": "GEMINI_LIVE"}

                # Strip markdown fences
                text = analysis_text.strip()
                if text.startswith("```"):
                    text = text.split("```", 2)[-1] if text.count("```") >= 2 else text
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.rstrip("`").strip()

                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    m = re.search(r"\{[\s\S]*\}", text)
                    if not m:
                        raise
                    parsed = json.loads(m.group(0))
                parsed["_source"] = "GEMINI_LIVE"
                parsed["_doc_type"] = doc_type
                parsed["_model"] = model_name
                parsed["_elapsed_sec"] = round(elapsed, 1)
                return parsed

            except json.JSONDecodeError as e:
                logger.error(f"Gemini JSON parse failed: {e} | raw: {analysis_text[:200]}")
                return {"error": "parse_failed", "source": "GEMINI_LIVE",
                        "raw_response": analysis_text[:500]}

            except Exception as e:
                err_str = str(e)
                is_quota = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()
                is_not_found = "404" in err_str or "not found" in err_str.lower()

                if is_not_found:
                    # This model doesn't exist — try the next one immediately
                    logger.warning(f"Gemini model {model_name} not found, trying next")
                    break

                if is_quota:
                    if attempt < MAX_RETRIES:
                        logger.warning(f"Gemini 429 quota hit on {model_name} — waiting {QUOTA_RETRY_WAIT}s before retry {attempt+1}/{MAX_RETRIES}")
                        time.sleep(QUOTA_RETRY_WAIT)
                    else:
                        logger.warning(f"Gemini quota exhausted on {model_name} — trying fallback model")
                        break  # try next model
                else:
                    logger.error(f"Gemini API error on {model_name} attempt {attempt}: {e}")
                    if attempt == MAX_RETRIES:
                        break  # try next model
                    time.sleep(5)

    # All models exhausted — return a graceful no-evidence result so adjudication
    # can still proceed without crashing, and the decision notes the parse failure.
    logger.error(f"Gemini [{doc_type}]: all models failed — returning quota_exhausted stub")
    return {
        "error": "quota_exhausted",
        "source": "GEMINI_LIVE",
        "note": "Gemini API quota exceeded. Evidence could not be parsed. Adjudication will proceed without document evidence.",
    }


# ── Public API ──────────────────────────────────────────────────────────────

def analyze_xray(image_b64: str) -> dict:
    """
    Send a chest X-ray image to MedGemma for radiological observation.
    Returns: {findings: [...], impression, confidence, limitations, _source}
    """
    result = _analyze(image_b64, PROMPT_XRAY, "xray")
    logger.info(f"X-ray analysis: {result.get('impression', result.get('error', '?'))}")
    return result


def analyze_lab_report(image_b64: str) -> dict:
    """
    Send a lab report image to MedGemma for structured data extraction.
    Returns: {patient_name_on_report, report_date, facility, results: [...], _source}
    """
    result = _analyze(image_b64, PROMPT_LAB, "lab_report")
    n = len(result.get("results", []))
    logger.info(f"Lab report: extracted {n} test results (confidence={result.get('extraction_confidence','?')})")
    return result


def analyze_invoice(image_b64: str) -> dict:
    """
    Send a medical invoice image to MedGemma for line-item extraction.
    Returns: {facility, invoice_date, items: [...], grand_total, _source}
    """
    result = _analyze(image_b64, PROMPT_INVOICE, "invoice")
    logger.info(f"Invoice: grand_total={result.get('grand_total', '?')}")
    return result


def classify_document(image_b64: str) -> dict:
    """
    Ask MedGemma to classify a document type (XRAY|LAB_REPORT|INVOICE|UNKNOWN).
    Returns: {doc_type, confidence, reasoning, _source}
    """
    result = _analyze(image_b64, PROMPT_CLASSIFY, "classify")
    logger.info(f"Doc classify: {result.get('doc_type','?')} (conf={result.get('confidence','?')})")
    return result


def health_check() -> dict:
    """Check if Gemini API key is configured."""
    gemini_key = os.getenv("gemini") or os.getenv("GEMINI_API_KEY")
    if gemini_key:
        return {"status": "ok", "message": "Gemini API key is configured"}
    else:
        return {"status": "error", "message": "Gemini API key is missing in .env"}


# ── Self-test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    print("=== MedGemma Client Health Check ===")
    result = health_check()
    print(json.dumps(result, indent=2))

    if result.get("status") != "ok":
        print("\n[ERROR] MedGemma not reachable. Set MEDGEMMA_API_URL in .env and start Colab notebook.")
        sys.exit(1)

    print("\n[OK] MedGemma is live and ready.")
