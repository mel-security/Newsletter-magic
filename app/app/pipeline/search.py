"""Autonomous web search engines — Google Search, Google News, Bing Search.

These searchers scrape public search result pages for cybersecurity queries.
No API keys required — uses HTML parsing of search result pages.
Results are returned as feed-compatible item dicts for the ingest pipeline.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin

from app.utils.http import http_client
from app.utils.logging import get_logger

log = get_logger("search")


# ── Default search queries for cybersecurity ──────────────
DEFAULT_QUERIES = [
    "cybersecurity vulnerability exploit",
    "ransomware attack today",
    "zero-day CVE",
    "data breach news",
    "APT threat actor campaign",
    "critical infrastructure cyber attack",
    "CISA advisory",
    "malware analysis report",
]


async def search_google(query: str, num_results: int = 10) -> list[dict]:
    """Search Google Web and extract result links + titles."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num_results}&hl=en"
    items = []

    try:
        async with http_client(headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        # Extract result blocks: <a href="/url?q=...">
        for match in re.finditer(
            r'<a\s+href="/url\?q=([^&"]+)&[^"]*"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        ):
            link = match.group(1)
            title_html = match.group(2)
            title = re.sub(r"<[^>]+>", "", title_html).strip()

            # Skip Google internal links
            if "google.com" in link or "googleapis.com" in link:
                continue
            if not link.startswith("http"):
                continue

            items.append({
                "title": title,
                "url": link,
                "summary": "",
                "published": "",
            })

        log.info("search.google.done", query=query, results=len(items))

    except Exception as exc:
        log.error("search.google.error", query=query, error=str(exc))

    return items[:num_results]


async def search_google_news(query: str, num_results: int = 10) -> list[dict]:
    """Search Google News RSS feed — no scraping needed."""
    rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    items = []

    try:
        import feedparser

        async with http_client(headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        }) as client:
            resp = await client.get(rss_url)
            resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:num_results]:
            items.append({
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "summary": getattr(entry, "summary", ""),
                "published": getattr(entry, "published", ""),
            })

        log.info("search.google_news.done", query=query, results=len(items))

    except Exception as exc:
        log.error("search.google_news.error", query=query, error=str(exc))

    return items


async def search_bing(query: str, num_results: int = 10) -> list[dict]:
    """Search Bing Web and extract result links + titles."""
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={num_results}"
    items = []

    try:
        async with http_client(headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        # Bing results are in <li class="b_algo"><h2><a href="...">
        for match in re.finditer(
            r'<li\s+class="b_algo"[^>]*>.*?<h2>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        ):
            link = match.group(1)
            title_html = match.group(2)
            title = re.sub(r"<[^>]+>", "", title_html).strip()

            if not link.startswith("http"):
                continue

            items.append({
                "title": title,
                "url": link,
                "summary": "",
                "published": "",
            })

        log.info("search.bing.done", query=query, results=len(items))

    except Exception as exc:
        log.error("search.bing.error", query=query, error=str(exc))

    return items[:num_results]


async def run_all_searches(
    queries: list[str] | None = None,
    engines: list[str] | None = None,
    results_per_query: int = 10,
) -> list[dict]:
    """Run searches across all enabled engines and return combined results.

    Args:
        queries: Search queries. Defaults to DEFAULT_QUERIES.
        engines: List of engines to use. Options: google, google_news, bing.
        results_per_query: Max results per query per engine.

    Returns:
        List of item dicts compatible with the ingest pipeline.
    """
    queries = queries or DEFAULT_QUERIES
    engines = engines or ["google_news", "bing"]

    engine_map = {
        "google": search_google,
        "google_news": search_google_news,
        "bing": search_bing,
    }

    all_items = []
    seen_urls = set()

    for query in queries:
        for engine_name in engines:
            func = engine_map.get(engine_name)
            if not func:
                log.warning("search.unknown_engine", engine=engine_name)
                continue

            items = await func(query, num_results=results_per_query)
            for item in items:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    item["_search_engine"] = engine_name
                    item["_search_query"] = query
                    all_items.append(item)

    log.info(
        "search.all_complete",
        total_items=len(all_items),
        queries=len(queries),
        engines=engines,
    )
    return all_items
