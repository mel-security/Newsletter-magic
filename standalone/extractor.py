"""Standalone content extractor — fetches full article text from URLs."""
from __future__ import annotations

import time
import random

import httpx
import trafilatura

from sanitizer import sanitize_text

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def fetch_article_text(url: str, timeout: int = 15) -> str | None:
    """Fetch and extract main text content from a URL using trafilatura."""
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        text = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        if not text:
            return None
        # Sanitize extracted text
        clean, report = sanitize_text(text, source=url)
        if report.get("blocked"):
            print(f"  [BLOCKED] Content from {url}: {report.get('reason', '')}")
            return None
        return clean
    except Exception as e:
        print(f"  [WARN] Failed to extract {url}: {e}")
        return None


def extract_articles(search_results: list[dict], max_articles: int = 50) -> list[dict]:
    """Fetch full text for search results. Returns enriched article dicts."""
    articles = []
    for i, item in enumerate(search_results[:max_articles]):
        url = item.get("url", "")
        title = item.get("title", "")
        print(f"  [{i+1}/{min(len(search_results), max_articles)}] Extracting: {title[:60]}...")

        text = fetch_article_text(url)
        if text and len(text) > 100:
            articles.append({
                "title": title,
                "url": url,
                "text": text,
                "source": item.get("source", item.get("engine", "")),
                "published": item.get("published", ""),
                "snippet": item.get("snippet", ""),
                "engine": item.get("engine", ""),
            })
        else:
            # Keep article with snippet only
            snippet = item.get("snippet", "")
            if snippet and len(snippet) > 50:
                articles.append({
                    "title": title,
                    "url": url,
                    "text": snippet,
                    "source": item.get("source", item.get("engine", "")),
                    "published": item.get("published", ""),
                    "snippet": snippet,
                    "engine": item.get("engine", ""),
                })

        # Be polite
        time.sleep(random.uniform(0.5, 1.5))

    print(f"  [OK] Extracted {len(articles)} articles with content")
    return articles
