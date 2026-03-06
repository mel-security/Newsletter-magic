"""Standalone article scorer — ranks articles by keyword relevance."""
from __future__ import annotations

import re


def score_articles(articles: list[dict], scoring_keywords: dict) -> list[dict]:
    """Score and sort articles by keyword matches.

    scoring_keywords format (from context.yml):
        critical: [list of keywords]   # weight 5
        high: [list of keywords]       # weight 3
        medium: [list of keywords]     # weight 1
    """
    weights = {"critical": 5, "high": 3, "medium": 1}

    for article in articles:
        score = 0
        matches = []
        searchable = f"{article.get('title', '')} {article.get('text', '')}".lower()

        for level, keywords in scoring_keywords.items():
            w = weights.get(level, 1)
            for kw in keywords:
                if kw.lower() in searchable:
                    score += w
                    matches.append(f"{kw} ({level})")

        # Bonus for longer content (more substance)
        text_len = len(article.get("text", ""))
        if text_len > 2000:
            score += 3
        elif text_len > 500:
            score += 1

        article["score"] = score
        article["score_matches"] = matches

    # Sort descending by score
    articles.sort(key=lambda a: a.get("score", 0), reverse=True)
    return articles
