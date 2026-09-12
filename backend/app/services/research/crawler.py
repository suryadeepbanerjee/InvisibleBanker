"""
Crawl4AI Live Research Crawler
================================
Two-phase crawler for live financial source research.

Phase A — Discovery:
  Given seed URLs from the source router, discover relevant links
  using BFS with URL/title/keyword relevance scoring.
  Returns scored URL list — does NOT fully process every page.

Phase B — Targeted Crawl:
  Crawl only the highest-scoring relevant pages.
  Max 10 pages per research job by default.
  Returns list of {url, title, content, authority, retrieval_time}.

Uses Crawl4AI 0.9.3 API (verified against installed package).

IMPORTANT: Does NOT crawl arbitrary user-supplied URLs.
  Only crawls domains present in the trusted sources registry.

Respects:
  - Domain restriction (DomainFilter)
  - URL pattern filtering (URLPatternFilter)
  - Keyword relevance scoring (KeywordRelevanceScorer)
  - Max pages limit
  - Crawl4AI's built-in robots.txt handling
"""
import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Maximum pages to crawl per research job
MAX_PAGES_PER_JOB = 10
# Minimum relevance score to qualify for Phase B crawl
MIN_RELEVANCE_SCORE = 0.3
# Crawl timeout per page (seconds)
PAGE_TIMEOUT = 20


def _extract_domain(url: str) -> str:
    """Extract base domain from URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _clean_html_text(text: str) -> str:
    """Basic text cleaning after crawl extraction."""
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove very short fragments
    if len(text) < 100:
        return ""
    return text[:8000]  # Cap for embedding cost control


def score_url_relevance(url: str, title: str, anchor_text: str, keywords: list[str]) -> float:
    """
    Heuristic relevance score for a discovered URL.
    Used to select which URLs to crawl in Phase B.

    Score: 0.0 (irrelevant) to 1.0 (highly relevant)
    """
    if not keywords:
        return 0.5  # Default if no keywords

    url_lower = url.lower()
    title_lower = (title or "").lower()
    anchor_lower = (anchor_text or "").lower()
    combined = f"{url_lower} {title_lower} {anchor_lower}"

    hits = sum(1 for kw in keywords if kw.lower() in combined)
    score = min(hits / max(len(keywords) * 0.3, 1), 1.0)

    # Penalize obviously irrelevant paths
    PENALTY_PATTERNS = [
        "/about", "/contact", "/career", "/privacy", "/terms",
        "/sitemap", "/media", "/press", "/csr", "/corporate",
        "login", "register", "signup",
    ]
    for pat in PENALTY_PATTERNS:
        if pat in url_lower:
            score *= 0.3
            break

    return round(score, 3)


async def _crawl_single_url(url: str, timeout: int = PAGE_TIMEOUT) -> Optional[dict]:
    """
    Crawl a single URL using Crawl4AI AsyncWebCrawler.
    Returns {url, title, content, markdown} or None on failure.
    """
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig

        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
        )
        run_config = CrawlerRunConfig(
            page_timeout=timeout * 1000,  # milliseconds
            wait_until="domcontentloaded",
            # Do not follow JS-heavy redirects that might load ads/tracking
            remove_overlay_elements=True,
            exclude_external_links=True,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            if result.success:
                content = result.markdown or result.extracted_content or ""
                content = _clean_html_text(content)
                return {
                    "url": url,
                    "title": result.metadata.get("title", "") if result.metadata else "",
                    "content": content,
                    "status_code": result.status_code,
                }
    except Exception as e:
        logger.warning(f"Crawl failed for {url}: {type(e).__name__}: {e}")
    return None


async def _discover_urls_bfs(
    seed_urls: list[str],
    allowed_domains: list[str],
    exclude_patterns: list[str],
    keywords: list[str],
    max_discovery: int = 30,
) -> list[dict]:
    """
    Phase A: BFS discovery of relevant URLs from seed URLs.
    Uses Crawl4AI BFSDeepCrawlStrategy with filters.

    Returns list of {url, title, score} sorted by relevance.
    """
    discovered = []

    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
        from crawl4ai.deep_crawling import (
            BFSDeepCrawlStrategy,
            KeywordRelevanceScorer,
            URLPatternFilter,
            DomainFilter,
            FilterChain,
        )

        # Build filters: restrict to allowed domains
        filters = []
        if allowed_domains:
            filters.append(DomainFilter(allowed_domains=allowed_domains))

        # Exclude irrelevant URL patterns
        if exclude_patterns:
            filters.append(URLPatternFilter(patterns=exclude_patterns, use_re=False))

        filter_chain = FilterChain(filters=filters) if filters else None

        # Keyword scorer for relevance-aware BFS
        scorer = KeywordRelevanceScorer(
            keywords=keywords,
            weight=0.7,
        ) if keywords else None

        strategy_kwargs = {
            "max_depth": 2,
            "max_pages": max_discovery,
        }
        if filter_chain:
            strategy_kwargs["filter_chain"] = filter_chain
        if scorer:
            strategy_kwargs["url_scorer"] = scorer

        strategy = BFSDeepCrawlStrategy(**strategy_kwargs)

        browser_config = BrowserConfig(headless=True, verbose=False)
        run_config = CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            page_timeout=15000,
            wait_until="domcontentloaded",
            remove_overlay_elements=True,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            for seed_url in seed_urls[:3]:  # Limit seed URLs to prevent explosion
                try:
                    results = await crawler.arun(url=seed_url, config=run_config)
                    # Handle both single result and list
                    if isinstance(results, list):
                        for r in results:
                            if r.url and r.url not in [d["url"] for d in discovered]:
                                title = r.metadata.get("title", "") if r.metadata else ""
                                score = score_url_relevance(r.url, title, "", keywords)
                                discovered.append({"url": r.url, "title": title, "score": score})
                    else:
                        # Single result from BFS entry point
                        if results.success:
                            title = results.metadata.get("title", "") if results.metadata else ""
                            score = score_url_relevance(results.url, title, "", keywords)
                            discovered.append({"url": results.url, "title": title, "score": score})
                except Exception as e:
                    logger.warning(f"BFS discovery error for {seed_url}: {e}")
                    # Fallback: add the seed URL itself
                    discovered.append({"url": seed_url, "title": seed_url, "score": 0.5})

    except ImportError as e:
        logger.error(f"Crawl4AI deep crawl import error: {e}")
        # Fallback: return seed URLs as discovered URLs
        for url in seed_urls:
            discovered.append({"url": url, "title": url, "score": 0.5})
    except Exception as e:
        logger.error(f"BFS discovery error: {e}")
        # Fallback: seed URLs
        for url in seed_urls:
            discovered.append({"url": url, "title": url, "score": 0.5})

    # Sort by relevance score descending
    discovered.sort(key=lambda x: x["score"], reverse=True)
    return discovered


async def research_intent(
    intent: str,
    query: str,
    sources: list[dict],
    keywords: list[str],
    max_pages: int = MAX_PAGES_PER_JOB,
) -> list[dict]:
    """
    Full two-phase research for a user intent.

    Phase A: Discover relevant URLs from trusted source seed URLs
    Phase B: Crawl top-scored pages for content

    Returns list of:
    {
        url, title, content, authority, source_id,
        relevance_score, retrieval_time, content_hash
    }
    """
    if not sources:
        logger.warning(f"No sources available for intent={intent}")
        return []

    start_time = time.time()

    # Collect seed URLs and domain restrictions from sources
    seed_urls = []
    allowed_domains = []
    exclude_patterns_all = []

    for source in sources:
        base_url = source.get("base_url", "")
        if not base_url:
            continue

        subpaths = source.get("crawl_subpaths") or []
        if subpaths:
            seed_urls.extend(subpaths[:3])  # Max 3 subpaths per source
        else:
            seed_urls.append(base_url)

        domain = _extract_domain(base_url)
        if domain not in allowed_domains:
            allowed_domains.append(domain)

        excludes = source.get("crawl_exclude_patterns") or []
        exclude_patterns_all.extend(excludes)

    if not seed_urls:
        logger.warning("No seed URLs extracted from sources")
        return []

    logger.info(
        f"Research phase A: intent={intent}, seeds={len(seed_urls)}, "
        f"domains={len(allowed_domains)}, keywords={len(keywords)}"
    )

    # Phase A: Discovery
    max_discovery = max_pages * 3  # Discover 3x more than we'll crawl
    discovered = await _discover_urls_bfs(
        seed_urls=seed_urls[:5],  # Cap seeds
        allowed_domains=allowed_domains,
        exclude_patterns=exclude_patterns_all,
        keywords=keywords,
        max_discovery=max_discovery,
    )

    # Phase B: Select top relevant pages and crawl them
    top_urls = [d for d in discovered if d["score"] >= MIN_RELEVANCE_SCORE][:max_pages]

    # If relevance filtering leaves too few, take top N regardless
    if len(top_urls) < 3:
        top_urls = discovered[:min(max_pages, len(discovered))]

    logger.info(
        f"Research phase B: discovered={len(discovered)}, "
        f"selected={len(top_urls)} pages to crawl"
    )

    # Build source authority mapping
    domain_to_source = {}
    for source in sources:
        domain = _extract_domain(source.get("base_url", ""))
        domain_to_source[domain] = source

    # Crawl selected pages
    results = []
    for item in top_urls:
        url = item["url"]
        crawled = await _crawl_single_url(url)
        if not crawled or not crawled.get("content"):
            logger.debug(f"Skipping empty result for {url}")
            continue

        # Determine source authority
        page_domain = _extract_domain(url)
        source_info = domain_to_source.get(page_domain, {})

        results.append({
            "url": url,
            "title": crawled["title"] or item["title"],
            "content": crawled["content"],
            "authority": source_info.get("name", page_domain),
            "source_id": source_info.get("id"),
            "category": source_info.get("category", "unknown"),
            "relevance_score": item["score"],
            "retrieval_time": datetime.now(timezone.utc).isoformat(),
            "content_hash": _content_hash(crawled["content"]),
        })

    elapsed = round(time.time() - start_time, 1)
    logger.info(
        f"Research complete: intent={intent}, pages_crawled={len(results)}, "
        f"elapsed={elapsed}s"
    )
    return results


def research_intent_sync(
    intent: str,
    query: str,
    sources: list[dict],
    keywords: list[str],
    max_pages: int = MAX_PAGES_PER_JOB,
) -> list[dict]:
    """
    Synchronous wrapper for research_intent.
    For use from non-async contexts (background threads).
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            research_intent(intent, query, sources, keywords, max_pages)
        )
    except Exception as e:
        logger.error(f"Sync research failed: {e}")
        return []
    finally:
        loop.close()
