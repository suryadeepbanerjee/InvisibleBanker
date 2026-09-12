"""
Research Orchestration Service
================================
Coordinates live web research for a user's financial problem.

Flow:
  1. Check if fresh cached knowledge exists for intent
  2. If fresh: skip crawl, use cached RAG
  3. If stale/missing: start async research job
  4. Research job: source router → Crawl4AI → embed → store knowledge → update job status
  5. Retrieved results are immediately available for RAG

The research runs in a background thread so the HTTP request remains responsive.
The chat route returns an interim response with research_status="ANALYZING" while the job runs.

Cache strategy:
  - Knowledge chunks are keyed by content_hash (dedup)
  - Freshness window: 72 hours for regulatory data, 168 hours for static scheme info
  - Cache miss → crawl → store → use immediately

IMPORTANT: Only crawls trusted domains from the sources registry.
"""
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.core.database import get_supabase_admin
from app.services.research.source_router import (
    get_sources_for_intent,
    get_crawl_keywords_for_intent,
    has_fresh_knowledge_for_intent,
)
from app.services.research.crawler import research_intent_sync
from app.services.knowledge.rag import embed_text

logger = logging.getLogger(__name__)

# Chunk size for splitting crawled content into knowledge chunks
CHUNK_WORD_SIZE = 400
CHUNK_OVERLAP = 40


def _chunk_text(text: str, size: int = CHUNK_WORD_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if len(words) <= size:
        return [text] if text.strip() else []
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + size])
        if chunk.strip():
            chunks.append(chunk)
        i += size - overlap
    return chunks


def _store_research_results(results: list[dict], job_id: str) -> int:
    """
    Embed and store crawled results into the knowledge table.
    Returns number of new chunks stored.
    """
    db = get_supabase_admin()
    stored = 0

    for result in results:
        content = result.get("content", "")
        if not content or len(content) < 100:
            continue

        chunks = _chunk_text(content)
        for i, chunk in enumerate(chunks):
            # Dedup by content hash
            import hashlib
            c_hash = hashlib.sha256(chunk.encode()).hexdigest()
            existing = db.table("knowledge").select("id").eq("content_hash", c_hash).execute()
            if existing.data:
                continue  # Already stored

            try:
                embedding = embed_text(chunk)
            except Exception as e:
                logger.error(f"Embedding failed for chunk {i}: {e}")
                continue

            db.table("knowledge").insert({
                "title": result["title"] or result["url"],
                "authority": result["authority"],
                "source_url": result["url"],
                "source_type": result.get("category", "unknown"),
                "content": chunk,
                "embedding": embedding,
                "version": 1,
                "content_hash": c_hash,
                "last_checked": result.get("retrieval_time", datetime.now(timezone.utc).isoformat()),
                "metadata": {
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "source_id": result.get("source_id"),
                    "job_id": job_id,
                    "relevance_score": result.get("relevance_score", 0.0),
                },
            }).execute()
            stored += 1

    return stored


def _run_research_job(job_id: str, domain: str, topic: str, task: str, query: str) -> None:
    """
    Background thread: execute a research job.
    Updates the research_jobs table with status throughout.
    """
    db = get_supabase_admin()

    def _update_job(updates: dict) -> None:
        try:
            db.table("research_jobs").update(updates).eq("id", job_id).execute()
        except Exception as e:
            logger.error(f"Failed to update research job {job_id}: {e}")

    try:
        _update_job({"status": "CRAWLING", "started_at": datetime.now(timezone.utc).isoformat()})

        # Get relevant sources
        sources = get_sources_for_intent(domain, topic, task)
        keywords = get_crawl_keywords_for_intent(domain, topic, task, query)

        if not sources:
            logger.warning(f"No sources found for topic={topic}, job={job_id}")
            _update_job({
                "status": "FAILED",
                "error_message": f"No crawl-enabled sources found for topic: {topic}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            return

        source_categories = list(set(s["category"] for s in sources))
        _update_job({
            "source_categories": source_categories,
            "pages_discovered": len(sources),
        })

        # Run live research
        results = research_intent_sync(
            intent=f"{domain}_{topic}",
            query=query,
            sources=sources,
            keywords=keywords,
        )

        _update_job({"status": "EMBEDDING", "pages_crawled": len(results)})

        # Store results as knowledge chunks
        chunks_stored = _store_research_results(results, job_id)

        _update_job({
            "status": "COMPLETE",
            "chunks_created": chunks_stored,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        # Mark conversation research as ready
        job_res = db.table("research_jobs").select("conversation_id").eq("id", job_id).execute()
        if job_res.data:
            conv_id = job_res.data[0].get("conversation_id")
            if conv_id:
                db.table("conversations").update({
                    "research_status": "READY",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", conv_id).execute()

        logger.info(f"Research job {job_id} complete: {chunks_stored} chunks stored from {len(results)} pages")

    except Exception as e:
        logger.error(f"Research job {job_id} failed: {e}", exc_info=True)
        _update_job({
            "status": "FAILED",
            "error_message": str(e)[:500],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        # Don't crash the conversation if research fails
        try:
            job_res = db.table("research_jobs").select("conversation_id").eq("id", job_id).execute()
            if job_res.data:
                conv_id = job_res.data[0].get("conversation_id")
                if conv_id:
                    db.table("conversations").update({
                        "research_status": "FAILED",
                    }).eq("id", conv_id).execute()
        except Exception:
            pass


def start_research_job(
    conversation_id: str,
    user_id: str,
    domain: str,
    topic: str,
    task: str,
    query: str,
) -> Optional[str]:
    """
    Create a research job and launch it in a background thread.
    Returns job_id.

    The job runs asynchronously — the caller should check status
    via the research_status field on the conversation record.
    """
    db = get_supabase_admin()
    job_id = str(uuid.uuid4())

    try:
        db.table("research_jobs").insert({
            "id": job_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "intent": f"{domain}_{topic}",
            "query": query,
            "status": "QUEUED",
        }).execute()

        # Mark conversation as researching
        db.table("conversations").update({
            "research_status": "ANALYZING",
            "latest_research_job_id": job_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", conversation_id).execute()

        # Launch background thread — non-blocking
        thread = threading.Thread(
            target=_run_research_job,
            args=(job_id, domain, topic, task, query),
            daemon=True,
            name=f"research-{job_id[:8]}",
        )
        thread.start()
        logger.info(f"Started research job {job_id} for topic={topic}")
        return job_id

    except Exception as e:
        logger.error(f"Failed to start research job: {e}")
        return None


def needs_live_research(domain: str, topic: str, task: str, conversation_id: str) -> bool:
    """
    Decide whether to trigger live research for this conversation turn.

    Returns True if:
      - Intent warrants research (not general_query/unknown for trivial messages)
      - No fresh cached knowledge exists
      - No active research job is already running for this conversation
    """
    if domain in ("unknown", "general"):
        return False

    # Check if fresh knowledge already exists
    if has_fresh_knowledge_for_intent(domain, topic, task):
        return False

    # Check if there's already a running job for this conversation
    db = get_supabase_admin()
    try:
        res = (
            db.table("research_jobs")
            .select("status")
            .eq("conversation_id", conversation_id)
            .limit(1)
            .execute()
        )
        if res.data:
            logger.info(f"Research already attempted for conversation {conversation_id}")
            return False
    except Exception as e:
        logger.warning(f"Could not check existing research jobs: {e}")

    return True


def get_job_status(conversation_id: str) -> Optional[dict]:
    """Get the latest research job status for a conversation."""
    db = get_supabase_admin()
    res = (
        db.table("research_jobs")
        .select("id, status, pages_crawled, chunks_created, error_message, completed_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None
