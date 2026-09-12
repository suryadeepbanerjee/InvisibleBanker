"""
RAG (Retrieval-Augmented Generation) Pipeline

Handles:
- Embedding generation via Gemini text-embedding-004 (HTTP-only, no torch/DLL needed)
- Vector search in Supabase pgvector
- Knowledge chunk retrieval with source metadata
- Evidence packaging for LLM context and UI display

WHY Gemini embeddings instead of sentence-transformers:
- sentence-transformers v3 requires torch which is blocked by Windows Application
  Control policy on this machine (OSError: shm.dll blocked)
- Gemini text-embedding-004 runs entirely over HTTP, requires zero local ML libraries
- Supports outputDimensionality=384 to match our existing pgvector schema (vector(384))
- Verified working 2026-09-11
"""
import hashlib
import logging
import json
from typing import Optional
import httpx
from app.core.database import get_supabase_admin
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GEMINI_EMBED_MODEL = "gemini-embedding-001"  # Verified working 2026-09-11, supports outputDimensionality=384
GEMINI_EMBED_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_EMBED_MODEL}:embedContent"
EMBEDDING_DIMENSION = 384  # Match pgvector schema (vector(384))


def embed_text(text: str) -> list[float]:
    """
    Generate embedding vector for text using Gemini text-embedding-004.

    Output dimension: 384 (to match existing pgvector schema).
    Uses HTTP only — no local ML libraries, no torch.
    """
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not configured — required for embeddings")

    try:
        payload = {
            "model": f"models/{GEMINI_EMBED_MODEL}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBEDDING_DIMENSION,
        }
        url = f"{GEMINI_EMBED_URL}?key={settings.gemini_api_key}"
        with httpx.Client(timeout=20) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embedding = data["embedding"]["values"]
            return embedding

    except httpx.HTTPStatusError as e:
        logger.error(f"Gemini embedding HTTP error {e.response.status_code}: {e.response.text[:200]}")
        raise
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise


def search_knowledge(
    query: str,
    top_k: int = 5,
    authority_filter: Optional[list[str]] = None,
) -> list[dict]:
    """
    Search the knowledge base using semantic similarity.

    Returns list of knowledge chunks with source metadata.
    Each chunk includes: content, title, authority, source_url, page_number, last_checked
    """
    try:
        query_embedding = embed_text(query)
        admin = get_supabase_admin()

        # Use Supabase RPC for vector similarity search
        params = {
            "query_embedding": query_embedding,
            "match_count": top_k,
        }
        if authority_filter:
            params["authority_filter"] = authority_filter

        result = admin.rpc("match_knowledge_chunks", params).execute()

        if not result.data:
            logger.info(f"No knowledge chunks found for query: {query[:100]}")
            return []

        return result.data

    except Exception as e:
        logger.error(f"Knowledge search failed: {e}")
        return []


def search_knowledge_for_product(product_name: str, query_context: str = "") -> list[dict]:
    """
    Retrieve knowledge chunks relevant to a specific financial product.
    """
    query = f"{product_name} eligibility criteria requirements {query_context}".strip()
    return search_knowledge(query, top_k=3)


def format_evidence_for_llm(chunks: list[dict]) -> str:
    """
    Format retrieved knowledge chunks as context for the LLM.

    Returns a formatted string with source citations.
    """
    if not chunks:
        return "No relevant source information retrieved."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        authority = chunk.get("authority", "Unknown")
        title = chunk.get("title", "Unknown Source")
        url = chunk.get("source_url", "")
        page = chunk.get("page_number", "")
        last_checked = chunk.get("last_checked", "")
        content = chunk.get("content", "")

        page_str = f", Page {page}" if page else ""
        date_str = f" (Last checked: {last_checked})" if last_checked else ""

        parts.append(
            f"[SOURCE {i}] {authority} — {title}{page_str}{date_str}\n"
            f"URL: {url}\n"
            f"Content: {content}"
        )

    return "\n\n---\n\n".join(parts)


def format_evidence_for_ui(chunks: list[dict]) -> list[dict]:
    """
    Format retrieved chunks for the frontend evidence viewer.

    Each item is inspectable in the UI with full source traceability.
    """
    evidence = []
    for chunk in chunks:
        evidence.append({
            "id": chunk.get("id", ""),
            "title": chunk.get("title", "Unknown Source"),
            "authority": chunk.get("authority", "Unknown"),
            "source_url": chunk.get("source_url", ""),
            "page_number": chunk.get("page_number"),
            "last_checked": str(chunk.get("last_checked", "")),
            "version": chunk.get("version", 1),
            "content_preview": chunk.get("content", "")[:300] + "..." if len(chunk.get("content", "")) > 300 else chunk.get("content", ""),
        })
    return evidence
