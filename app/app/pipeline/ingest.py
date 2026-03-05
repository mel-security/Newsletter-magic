"""Ingest RSS/JSON sources into raw_items."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RawItem
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


async def ingest_sources(session: Session, max_items: int | None = None) -> dict:
    """Fetch all configured sources and store raw items."""
    sources = load_sources()
    stats = {"sources": 0, "items_fetched": 0, "items_new": 0, "errors": 0}
    max_items = max_items or settings.max_articles_per_run

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
                raw_url = item.get("url") or item.get("link", "")
                if not raw_url:
                    continue

                canonical = canonicalize_url(raw_url)

                # Check if already exists
                existing = session.execute(
                    select(RawItem).where(RawItem.url == canonical)
                ).scalar_one_or_none()

                if existing:
                    continue

                raw_item = RawItem(
                    source=src["name"],
                    url=canonical,
                    raw={
                        "title": item.get("title", ""),
                        "summary": item.get("summary", ""),
                        "published": item.get("published", ""),
                        "source_reliability": src.get("reliability", 0.5),
                        "lang": src.get("lang", "en"),
                    },
                    status="new",
                )
                session.add(raw_item)
                stats["items_new"] += 1
                stats["items_fetched"] += 1

            log.info("ingest.source_done", source=src["name"], items=len(items))

        except Exception as exc:
            stats["errors"] += 1
            log.error("ingest.source_error", source=src["name"], error=str(exc))

    session.commit()
    log.info("ingest.complete", **stats)
    return stats
