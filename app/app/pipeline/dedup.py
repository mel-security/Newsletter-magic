"""Deduplicate articles by URL canonicalization and content similarity."""
from __future__ import annotations

from simhash import Simhash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article
from app.utils.logging import get_logger

log = get_logger("dedup")

_SIMHASH_THRESHOLD = 5  # Hamming distance threshold for near-duplicates


def _get_features(text: str) -> list[str]:
    """Extract shingle features for simhash."""
    width = 3
    words = text.lower().split()
    return [" ".join(words[i : i + width]) for i in range(max(len(words) - width + 1, 1))]


def _simhash_distance(h1: Simhash, h2: Simhash) -> int:
    return h1.distance(h2)


def deduplicate_articles(session: Session) -> dict:
    """Mark near-duplicate articles. Keeps the first-seen article."""
    stats = {"checked": 0, "duplicates_found": 0}

    articles = session.execute(
        select(Article).where(Article.story_id.is_(None)).order_by(Article.published_at.asc())
    ).scalars().all()

    if not articles:
        return stats

    seen_hashes: list[tuple[Simhash, Article]] = []

    for article in articles:
        stats["checked"] += 1

        if not article.text:
            continue

        current_hash = Simhash(_get_features(article.text))
        is_dup = False

        for existing_hash, existing_article in seen_hashes:
            dist = _simhash_distance(current_hash, existing_hash)
            if dist <= _SIMHASH_THRESHOLD:
                # Mark as duplicate by giving it the same content_hash
                article.content_hash = existing_article.content_hash
                is_dup = True
                stats["duplicates_found"] += 1
                log.debug(
                    "dedup.near_duplicate",
                    dup_url=article.url,
                    orig_url=existing_article.url,
                    distance=dist,
                )
                break

        if not is_dup:
            seen_hashes.append((current_hash, article))

    session.commit()
    log.info("dedup.complete", **stats)
    return stats
