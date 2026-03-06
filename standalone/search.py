"""Standalone search module — scrapes Google News, Google Search, Bing."""
from __future__ import annotations

import re
import time
import random
from urllib.parse import quote_plus, urljoin, urlparse

import httpx
import feedparser
from bs4 import BeautifulSoup

from sanitizer import sanitize_text

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def _headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _polite_delay():
    time.sleep(random.uniform(1.0, 2.5))


# ── Google News (RSS) ───────────────────────────────────────────

def search_google_news(query: str, lang: str = "en", max_results: int = 8) -> list[dict]:
    """Fetch results from Google News RSS."""
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={lang}&gl=US&ceid=US:{lang}"
    results = []
    try:
        resp = httpx.get(url, headers=_headers(), timeout=15, follow_redirects=True)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:max_results]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published = entry.get("published", "")
            source = entry.get("source", {}).get("title", "")
            clean_title, _ = sanitize_text(title, source="google_news")
            if clean_title and link:
                results.append({
                    "title": clean_title,
                    "url": link,
                    "source": source,
                    "published": published,
                    "engine": "google_news",
                })
    except Exception as e:
        print(f"  [WARN] Google News search failed: {e}")
    return results


# ── Google Search (HTML scrape) ─────────────────────────────────

def search_google(query: str, max_results: int = 8) -> list[dict]:
    """Scrape Google search results."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results}"
    results = []
    try:
        resp = httpx.get(url, headers=_headers(), timeout=15, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        for div in soup.select("div.g, div[data-hveid]"):
            a_tag = div.find("a", href=True)
            if not a_tag:
                continue
            href = a_tag["href"]
            if href.startswith("/url?q="):
                href = href.split("/url?q=")[1].split("&")[0]
            if not href.startswith("http"):
                continue
            title_el = div.find("h3")
            title = title_el.get_text(strip=True) if title_el else ""
            snippet_el = div.find("div", class_="VwiC3b") or div.find("span", class_="st")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            clean_title, _ = sanitize_text(title, source="google")
            clean_snippet, _ = sanitize_text(snippet, source="google")
            if clean_title and href:
                results.append({
                    "title": clean_title,
                    "url": href,
                    "snippet": clean_snippet,
                    "engine": "google",
                })
    except Exception as e:
        print(f"  [WARN] Google search failed: {e}")
    return results


# ── Bing Search (HTML scrape) ───────────────────────────────────

def search_bing(query: str, max_results: int = 8) -> list[dict]:
    """Scrape Bing search results."""
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={max_results}"
    results = []
    try:
        resp = httpx.get(url, headers=_headers(), timeout=15, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        for li in soup.select("li.b_algo"):
            a_tag = li.find("a", href=True)
            if not a_tag:
                continue
            href = a_tag["href"]
            if not href.startswith("http"):
                continue
            title = a_tag.get_text(strip=True)
            snippet_el = li.find("p") or li.find("div", class_="b_caption")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            clean_title, _ = sanitize_text(title, source="bing")
            clean_snippet, _ = sanitize_text(snippet, source="bing")
            if clean_title and href:
                results.append({
                    "title": clean_title,
                    "url": href,
                    "snippet": clean_snippet,
                    "engine": "bing",
                })
    except Exception as e:
        print(f"  [WARN] Bing search failed: {e}")
    return results


# ── Run all searches ────────────────────────────────────────────

ENGINE_MAP = {
    "google_news": search_google_news,
    "google": search_google,
    "bing": search_bing,
}


def run_searches(queries: list[str], engines: list[str], results_per_query: int = 8, lang: str = "en") -> list[dict]:
    """Run all search queries across all configured engines. Returns deduplicated results."""
    all_results = []
    seen_urls = set()

    for query in queries:
        for engine_name in engines:
            fn = ENGINE_MAP.get(engine_name)
            if not fn:
                print(f"  [WARN] Unknown engine: {engine_name}")
                continue
            print(f"  Searching [{engine_name}]: {query}")
            if engine_name == "google_news":
                items = fn(query, lang=lang, max_results=results_per_query)
            else:
                items = fn(query, max_results=results_per_query)

            for item in items:
                url = item["url"]
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(item)

            _polite_delay()

    print(f"  [OK] {len(all_results)} unique results from {len(queries)} queries x {len(engines)} engines")
    return all_results
