"""Ingest RSS/JSON sources + autonomous web searches into raw_items."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RawItem
from app.pipeline.sanitizer import sanitize_feed_item
from app.settings import settings
from app.utils.http import http_client
from app.utils.logging import get_logger
from app.utils.text import canonicalize_url

log = get_logger("ingest")


def load_sources() -> list[dict]:
    sources_path = Path(settings.config_dir) / "sources.yml"
    with open(sources_path) as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def load_search_config() -> dict:
    """Load search engine queries and settings."""
    path = Path(settings.config_dir) / "search_queries.yml"
    if not path.exists():
        return {"enabled_engines": [], "queries": [], "results_per_query": 10}
    with open(path) as f:
        return yaml.safe_load(f) or {}


async def fetch_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS feed."""
    async with http_client() as client:
        resp = await client.get(url)
        resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    items = []
    for entry in feed.entries:
        items.append({
            "title": getattr(entry, "title", ""),
            "url": getattr(entry, "link", ""),
            "published": getattr(entry, "published", ""),
            "summary": getattr(entry, "summary", ""),
        })
    return items


async def fetch_json_feed(url: str) -> list[dict]:
    """Fetch a JSON feed."""
    async with http_client() as client:
        resp = await client.get(url)
        resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    return [data]


def _store_item(
    session: Session,
    item: dict,
    source_name: str,
    reliability: float,
    lang: str,
    stats: dict,
) -> None:
    """Sanitize and store a single feed item into raw_items."""
    raw_url = item.get("url") or item.get("link", "")
    if not raw_url:
        return

    canonical = canonicalize_url(raw_url)

    # Check if already exists
    existing = session.execute(
        select(RawItem).where(RawItem.url == canonical)
    ).scalar_one_or_none()
    if existing:
        return

    # ── Sanitize before storing ──────────────────────────
    sanitized_item, san_report = sanitize_feed_item(item, source=source_name)
    if san_report["rejected"]:
        log.warning(
            "ingest.item_rejected",
            source=source_name,
            url=canonical,
            reason="prompt_injection_detected",
        )
        stats["sanitizer_rejected"] = stats.get("sanitizer_rejected", 0) + 1
        return

    raw_item = RawItem(
        source=source_name,
        url=canonical,
        raw={
            "title": sanitized_item.get("title", ""),
            "summary": sanitized_item.get("summary", ""),
            "published": sanitized_item.get("published", ""),
            "source_reliability": reliability,
            "lang": lang,
        },
        status="new",
    )
    session.add(raw_item)
    stats["items_new"] += 1
    stats["items_fetched"] += 1


async def ingest_sources(session: Session, max_items: int | None = None) -> dict:
    """Fetch all configured sources and store raw items."""
    sources = load_sources()
    stats = {
        "sources": 0, "items_fetched": 0, "items_new": 0,
        "errors": 0, "sanitizer_rejected": 0,
        "search_engines": 0, "search_items": 0,
    }
    max_items = max_items or settings.max_articles_per_run

    # ── Phase 1: RSS/JSON feeds ──────────────────────────
    for src in sources:
        try:
            if src["type"] == "rss":
                items = await fetch_rss(src["url"])
            elif src["type"] == "json":
                items = await fetch_json_feed(src["url"])
            else:
                log.warning("ingest.unknown_type", source=src["name"], type=src["type"])
                continue

            stats["sources"] += 1

            for item in items[:max_items]:
                _store_item(
                    session, item,
                    source_name=src["name"],
                    reliability=src.get("reliability", 0.5),
                    lang=src.get("lang", "en"),
                    stats=stats,
                )

            log.info("ingest.source_done", source=src["name"], items=len(items))

        except Exception as exc:
            stats["errors"] += 1
            log.error("ingest.source_error", source=src["name"], error=str(exc))

    # ── Phase 2: Autonomous web searches ─────────────────
    if settings.search_enabled:
        try:
            from app.pipeline.search import run_all_searches

            search_cfg = load_search_config()
            engines = search_cfg.get("enabled_engines", ["google_news", "bing"])
            queries = search_cfg.get("queries")
            rpp = search_cfg.get("results_per_query", 10)

            log.info("ingest.search.start", engines=engines, queries=len(queries or []))
            search_items = await run_all_searches(
                queries=queries,
                engines=engines,
                results_per_query=rpp,
            )

            stats["search_engines"] = len(engines)

            for item in search_items[:max_items]:
                engine = item.pop("_search_engine", "search")
                query = item.pop("_search_query", "")
                _store_item(
                    session, item,
                    source_name=f"search:{engine}",
                    reliability=0.6,  # search results get moderate reliability
                    lang="en",
                    stats=stats,
                )
                stats["search_items"] += 1

            log.info("ingest.search.done", items=len(search_items))

        except Exception as exc:
            stats["errors"] += 1
            log.error("ingest.search.error", error=str(exc))

    session.commit()
    log.info("ingest.complete", **stats)
    return stats
