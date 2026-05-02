"""
rag_engine.py — FAISS-based RAG for policy document retrieval

Loads policy vector index, performs semantic search for relevant
policy clauses, and formats context for GLM prompt injection.
"""

import os
import json
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("claimiq.rag")

INDEX_PATH = os.getenv("FAISS_INDEX_PATH", ".tmp/policy_index")

# Global cache
_index = None
_documents = None
_model = None


def _get_embedding_model():
    """Lazy-load sentence transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded: all-MiniLM-L6-v2")
        except Exception as e:
            logger.warning(f"Sentence-transformers unavailable; RAG semantic search disabled: {e}")
            return None
    return _model


def build_index(documents: list[dict]):
    """
    Build FAISS index from policy documents.
    Each doc: {"id": str, "title": str, "content": str, "category": str}
    """
    import faiss
    import numpy as np

    model = _get_embedding_model()
    if model is None:
        raise RuntimeError("Sentence-transformers unavailable; cannot build FAISS index.")
    texts = [d["content"] for d in documents]
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # Inner product (cosine sim with normalized vectors)
    index.add(embeddings.astype(np.float32))

    os.makedirs(INDEX_PATH, exist_ok=True)
    faiss.write_index(index, os.path.join(INDEX_PATH, "policy.index"))
    with open(os.path.join(INDEX_PATH, "documents.json"), "w") as f:
        json.dump(documents, f, indent=2)

    logger.info(f"Built FAISS index: {len(documents)} documents, dim={dim}")
    return index


def load_index():
    """Load pre-built FAISS index and documents."""
    global _index, _documents
    try:
        import faiss
    except Exception as e:
        logger.warning(f"FAISS unavailable; RAG index disabled: {e}")
        return None

    idx_path = os.path.join(INDEX_PATH, "policy.index")
    doc_path = os.path.join(INDEX_PATH, "documents.json")

    if not os.path.exists(idx_path):
        logger.warning(f"No FAISS index at {idx_path}. Run build_policy_index.py first.")
        return None

    _index = faiss.read_index(idx_path)
    with open(doc_path) as f:
        _documents = json.load(f)
    logger.info(f"Loaded FAISS index: {len(_documents)} documents")
    return _index


def search(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over policy documents."""
    global _index, _documents
    if _index is None:
        load_index()
    if _index is None:
        return []

    model = _get_embedding_model()
    if model is None:
        return []
    import numpy as np
    q_emb = model.encode([query], normalize_embeddings=True).astype(np.float32)
    scores, indices = _index.search(q_emb, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < len(_documents):
            doc = _documents[idx].copy()
            doc["relevance_score"] = float(score)
            results.append(doc)
    return results


def get_policy_context(claim_data: dict, top_k: int = 5) -> str:
    """
    Build policy context string for GLM adjudication.
    Searches using diagnosis + procedures as query.
    """
    diagnosis = claim_data.get("diagnosis", "")
    procedures_list = claim_data.get("procedures") or []
    procedures = ", ".join(procedures_list) if isinstance(procedures_list, list) else str(procedures_list)
    
    meds_list = claim_data.get("medications") or []
    medications = ", ".join(
        m.get("name", "") if isinstance(m, dict) else str(m)
        for m in meds_list
    )
    query = f"{diagnosis} {procedures} {medications}".strip()
    if not query:
        query = "general medical claim coverage"

    results = search(query, top_k=top_k)
    if not results:
        return (
            "No matching policy documents found for this claim. "
            "Apply the following general Malaysian TPA principles:\n"
            "- PMCare outpatient GP consultation limit: RM 35–80 per visit\n"
            "- Medications: covered up to RM 50 per visit for generic formulary drugs\n"
            "- Lab investigations: covered if clinically indicated with documented diagnosis\n"
            "- Inpatient: pre-authorisation required for admissions > 24h\n"
            "- Timely filing: claims must be submitted within 14 days of service date\n"
            "- Duplicate claims: not payable (CARC 18)\n"
            "- Non-covered: cosmetic procedures, experimental treatments, self-inflicted injuries"
        )

    context_parts = []
    for i, doc in enumerate(results, 1):
        context_parts.append(
            f"### Policy Excerpt {i} (Relevance: {doc['relevance_score']:.2f})\n"
            f"**{doc.get('title', 'Untitled')}** [{doc.get('category', '')}]\n\n"
            f"{doc['content']}\n"
        )
    return "\n---\n".join(context_parts)
