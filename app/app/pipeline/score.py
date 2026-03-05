"""Score articles based on configurable weights."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article
from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("score")


def load_scoring_config() -> dict:
    path = Path(settings.config_dir) / "scoring.yml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_keywords() -> dict:
    path = Path(settings.config_dir) / "keywords.yml"
    with open(path) as f:
        return yaml.safe_load(f)


def _recency_factor(article: Article, config: dict) -> float:
    """Score based on how recent the article is."""
    if not article.published_at:
        return 0.3  # Unknown date gets partial credit

    age_hours = (datetime.now(timezone.utc) - article.published_at.replace(
        tzinfo=timezone.utc if article.published_at.tzinfo is None else article.published_at.tzinfo
    )).total_seconds() / 3600

    max_age = config["weights"]["recency"]["max_age_hours"]
    decay = config["weights"]["recency"]["decay_hours"]

    if age_hours > max_age:
        return 0.0
    if age_hours <= decay:
        return 1.0
    return max(0.0, 1.0 - (age_hours - decay) / (max_age - decay))


def _keyword_factor(text: str, keywords: dict) -> float:
    """Score based on keyword matches."""
    text_lower = text.lower()
    total = 0.0

    for category_name, category in keywords.items():
        if not isinstance(category, dict) or "terms" not in category:
            continue
        weight = category.get("weight", 1.0)
        for term in category["terms"]:
            if term.lower() in text_lower:
                total += weight
                break  # One match per category is enough

    return min(total / 10.0, 1.0)  # Normalize to 0-1


def _source_reliability(article: Article, sources_config: list[dict] | None = None) -> float:
    """Get source reliability from config."""
    if sources_config:
        for src in sources_config:
            if src["name"] == article.source:
                return src.get("reliability", 0.5)
    return 0.5


def score_articles(session: Session) -> dict:
    """Score all unscored articles."""
    stats = {"scored": 0}
    config = load_scoring_config()
    keywords = load_keywords()
    weights = config["weights"]

    from app.pipeline.ingest import load_sources
    sources = load_sources()

    articles = session.execute(
        select(Article).where(Article.score == 0).where(Article.text.isnot(None))
    ).scalars().all()

    for article in articles:
        combined_text = f"{article.title or ''} {article.text or ''}"

        recency = _recency_factor(article, config) * weights["recency"]["weight"]
        reliability = _source_reliability(article, sources) * weights["source_reliability"]["weight"]
        kw_score = _keyword_factor(combined_text, keywords) * weights["keyword_match"]["weight"]

        # KEV presence
        kev = 0.0
        for term in ["known exploited", "KEV", "CISA KEV"]:
            if term.lower() in combined_text.lower():
                kev = weights["kev_presence"]["weight"]
                break

        # Exploit hints
        exploit = 0.0
        for term in ["proof of concept", "PoC", "exploit code", "weaponized"]:
            if term.lower() in combined_text.lower():
                exploit = weights["exploit_hint"]["weight"]
                break

        # CVE count
        from app.pipeline.extract import extract_cves_from_text
        cves = extract_cves_from_text(combined_text)
        cve_factor = min(len(cves), weights["cve_count"]["cap"]) / weights["cve_count"]["cap"]
        cve_score = cve_factor * weights["cve_count"]["weight"]

        # Ransomware/leak
        ransom = 0.0
        for term in ["ransomware", "data leak", "data breach", "dark web"]:
            if term.lower() in combined_text.lower():
                ransom = weights["ransomware_leak"]["weight"]
                break

        raw_score = recency + reliability + kw_score + kev + exploit + cve_score + ransom
        max_possible = sum(w["weight"] for w in weights.values())
        normalized = min(100.0, (raw_score / max_possible) * 100)

        article.score = round(normalized, 2)
        stats["scored"] += 1

    session.commit()
    log.info("score.complete", **stats)
    return stats
