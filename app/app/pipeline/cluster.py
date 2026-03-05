"""Cluster articles into stories by shared CVEs and entity overlap."""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article, Story
from app.pipeline.extract import extract_cves_from_text
from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("cluster")


def _title_words(title: str) -> set[str]:
    """Extract significant words from a title for overlap detection."""
    stop_words = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
        "is", "are", "was", "were", "be", "been", "being", "with", "by",
        "le", "la", "les", "de", "des", "du", "un", "une", "et", "en",
    }
    words = set()
    for w in (title or "").lower().split():
        w = w.strip(".,;:!?\"'()[]{}")
        if len(w) > 2 and w not in stop_words:
            words.add(w)
    return words


def cluster_into_stories(session: Session) -> dict:
    """Group unclustered articles into stories."""
    stats = {"articles_processed": 0, "stories_created": 0, "stories_updated": 0}

    # Get unclustered articles sorted by score descending
    articles = session.execute(
        select(Article)
        .where(Article.story_id.is_(None))
        .where(Article.text.isnot(None))
        .order_by(Article.score.desc())
    ).scalars().all()

    if not articles:
        return stats

    # Build CVE-to-articles map
    cve_groups: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        cves = extract_cves_from_text(f"{article.title or ''} {article.text or ''}")
        for cve in cves:
            cve_groups[cve].append(article)

    # Group by shared CVEs first
    assigned: set[uuid.UUID] = set()
    clusters: list[list[Article]] = []

    for cve, cve_articles in cve_groups.items():
        cluster = [a for a in cve_articles if a.id not in assigned]
        if cluster:
            clusters.append(cluster)
            for a in cluster:
                assigned.add(a.id)

    # Group remaining by title overlap
    remaining = [a for a in articles if a.id not in assigned]
    for article in remaining:
        title_words = _title_words(article.title)
        matched = False

        for cluster in clusters:
            for existing in cluster:
                existing_words = _title_words(existing.title)
                overlap = title_words & existing_words
                if len(overlap) >= 3:
                    cluster.append(article)
                    assigned.add(article.id)
                    matched = True
                    break
            if matched:
                break

        if not matched:
            clusters.append([article])
            assigned.add(article.id)

    # Create/update stories
    for cluster in clusters:
        stats["articles_processed"] += len(cluster)

        # Use highest-scored article's title as canonical
        best = max(cluster, key=lambda a: a.score)
        max_score = best.score

        # Determine severity from scoring config
        if max_score >= 80:
            severity = "critical"
        elif max_score >= 60:
            severity = "high"
        elif max_score >= 40:
            severity = "medium"
        else:
            severity = "low"

        story = Story(
            canonical_title=best.title or "Untitled Story",
            severity=severity,
            tags=[],
            summary=best.text[:500] if best.text else None,
        )
        session.add(story)
        session.flush()  # Get story.id

        for article in cluster:
            article.story_id = story.id

        stats["stories_created"] += 1

    session.commit()
    log.info("cluster.complete", **stats)
    return stats
