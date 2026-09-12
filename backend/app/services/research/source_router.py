"""
Source Router
=============
Maps user intent to relevant authoritative source categories,
then retrieves matching sources from the Supabase `sources` table.

This is the component that prevents the system from crawling irrelevant
pages (e.g., home loans when the user asks about a failed UPI payment).

Architecture:
  USER INTENT
    → source categories (e.g., ["bank", "msme", "govt_scheme"])
    → filter sources table by category
    → return sources with their crawl configuration

No hardcoded scheme lists. The sources table is the source of truth.
"""
import logging
from typing import Optional
from app.core.database import get_supabase_admin

logger = logging.getLogger(__name__)


# ─── Intent → Source Category Mapping ────────────────────────────────────────

# Maps classified intents to relevant source categories in the sources table.
# Source categories must match the `category` column in the sources table.
# Maps classified domains to relevant source categories in the sources table.
DOMAIN_SOURCE_MAP: dict[str, list[str]] = {
    "financing": ["bank", "msme", "nbfc", "regulatory"],
    "government_scheme": ["govt_scheme", "msme", "regulatory", "bank"],
    "payment": ["regulatory", "bank", "grievance"],
    "insurance": ["insurance", "govt_scheme", "regulatory"],
    "general": ["regulatory", "bank", "govt_scheme"],
    "unknown": ["regulatory"],
}


def get_source_categories_for_intent(domain: str, topic: str) -> list[str]:
    """
    Return the source categories relevant to this domain/topic.
    """
    categories = DOMAIN_SOURCE_MAP.get(domain, DOMAIN_SOURCE_MAP["unknown"]).copy()
    topic_lower = topic.lower()
    if "housing" in topic_lower or "home" in topic_lower or "pmay" in topic_lower or "awas" in topic_lower:
        categories.append("housing_finance")
    return list(set(categories))


def get_crawl_keywords_for_intent(domain: str, topic: str, task: str, query: str) -> list[str]:
    """Return keyword hints for crawl relevance scoring based on domain/topic/task."""
    keywords = topic.split()
    if task == "eligibility":
        keywords.extend(["eligibility", "qualify", "criteria"])
    elif task == "documents":
        keywords.extend(["documents", "required", "proof", "kyc"])
    elif task == "application":
        keywords.extend(["apply", "online", "application", "form", "portal"])
    elif task == "grievance":
        keywords.extend(["complaint", "grievance", "dispute", "ombudsman"])
    return list(set(keywords))


def get_sources_for_intent(
    domain: str,
    topic: str,
    task: str,
    state: Optional[str] = None,
    limit: int = 8,
) -> list[dict]:
    """
    Query the sources table for sources relevant to this intent.

    Returns sources ordered by authority_level (highest first).
    Only returns crawl_enabled sources.
    """
    categories = get_source_categories_for_intent(domain, topic)
    db = get_supabase_admin()

    try:
        res = (
            db.table("sources")
            .select(
                "id, name, category, authority_level, base_url, "
                "crawl_enabled, crawl_subpaths, crawl_exclude_patterns, "
                "product_data, regulatory_data, scheme_data, "
                "last_crawled, last_crawl_status, chunks_count, notes"
            )
            .in_("category", categories)
            .eq("crawl_enabled", True)
            .order("authority_level", desc=True)
            .limit(limit)
            .execute()
        )
        sources = res.data or []
        logger.info(
            f"Source router: intent={intent}, categories={categories}, "
            f"found={len(sources)} sources"
        )
        return sources

    except Exception as e:
        logger.error(f"Source router DB error: {e}")
        return []


def get_all_sources_for_intent(
    intent: str,
    crawl_enabled_only: bool = False,
) -> list[dict]:
    """
    Get ALL sources for intent without limiting.
    Used for reporting and debugging.
    """
    categories = get_source_categories_for_intent(intent)
    db = get_supabase_admin()

    try:
        q = (
            db.table("sources")
            .select("id, name, category, authority_level, base_url, crawl_enabled")
            .in_("category", categories)
            .order("authority_level", desc=True)
        )
        if crawl_enabled_only:
            q = q.eq("crawl_enabled", True)

        res = q.execute()
        return res.data or []

    except Exception as e:
        logger.error(f"Source router (all) DB error: {e}")
        return []


def has_fresh_knowledge_for_intent(
    domain: str,
    topic: str,
    task: str,
    fresh_hours: int = 72,
) -> bool:
    """
    Check if there's already fresh cached knowledge for this topic.
    Used to decide whether a live crawl is needed.

    A knowledge chunk is "fresh" if last_checked within fresh_hours.
    """
    db = get_supabase_admin()
    try:
        # Check if any knowledge chunks exist for the topic's source categories
        categories = get_source_categories_for_intent(domain, topic)

        res = (
            db.table("knowledge")
            .select("id")
            .in_("source_type", categories)
            .gte(
                "last_checked",
                f"now() - interval '{fresh_hours} hours'",
            )
            .limit(1)
            .execute()
        )
        has_fresh = bool(res.data)
        logger.info(f"Fresh knowledge check for intent={intent}: {has_fresh}")
        return has_fresh
    except Exception as e:
        logger.warning(f"Fresh knowledge check failed: {e}")
        return False  # Conservative: assume we need to crawl
