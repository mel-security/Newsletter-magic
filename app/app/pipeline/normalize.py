"""Extract full text from raw items and normalize."""
from __future__ import annotations

from datetime import datetime, timezone

import trafilatura
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article, RawItem
from app.pipeline.sanitizer import sanitize_text
from app.settings import settings
from app.utils.http import http_client
from app.utils.logging import get_logger
from app.utils.text import canonicalize_url, content_hash

log = get_logger("normalize")


async def extract_full_text(url: str) -> str | None:
    """Download page and extract main text content."""
    try:
        async with http_client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
        text = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        return text
    except Exception as exc:
        log.warning("normalize.extract_fail", url=url, error=str(exc))
        return None


def detect_language(text: str) -> str:
    """Simple language detection heuristic."""
    fr_words = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "est", "en", "dans", "pour", "sur"}
    words = set(text.lower().split()[:100])
    fr_count = len(words & fr_words)
    return "fr" if fr_count >= 5 else "en"


async def normalize_raw_items(session: Session) -> dict:
    """Process raw items into articles with full text."""
    stats = {"processed": 0, "articles_created": 0, "skipped": 0, "errors": 0, "sanitizer_rejected": 0}

    raw_items = session.execute(
        select(RawItem).where(RawItem.status == "new")
    ).scalars().all()

    for raw in raw_items:
        try:
            # Check if article already exists
            existing = session.execute(
                select(Article).where(Article.url == raw.url)
            ).scalar_one_or_none()

            if existing:
                raw.status = "duplicate"
                stats["skipped"] += 1
                continue

            # Extract full text
            full_text = await extract_full_text(raw.url)

            if not full_text:
                # Fall back to summary
                full_text = (raw.raw or {}).get("summary", "")

            if not full_text:
                raw.status = "no_content"
                stats["skipped"] += 1
                continue

            # ── Sanitize extracted text (prompt injection defense) ──
            full_text, san_report = sanitize_text(
                full_text, source=raw.url, strict=False
            )
            if san_report["action"] == "rejected":
                raw.status = "sanitizer_rejected"
                stats["sanitizer_rejected"] += 1
                log.warning("normalize.sanitizer_rejected", url=raw.url)
                continue

            lang = detect_language(full_text)
            c_hash = content_hash(full_text)

            # Parse published date
            published_str = (raw.raw or {}).get("published", "")
            published_at = None
            if published_str:
                try:
                    from email.utils import parsedate_to_datetime
                    published_at = parsedate_to_datetime(published_str)
                except Exception:
                    pass

            article = Article(
                url=raw.url,
                title=(raw.raw or {}).get("title", ""),
                published_at=published_at,
                source=raw.source,
                text=full_text,
                lang=lang,
                content_hash=c_hash,
            )
            session.add(article)
            raw.status = "processed"
            stats["articles_created"] += 1

        except Exception as exc:
            raw.status = "error"
            stats["errors"] += 1
            log.error("normalize.error", url=raw.url, error=str(exc))

        stats["processed"] += 1

    session.commit()
    log.info("normalize.complete", **stats)
    return stats
