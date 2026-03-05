"""Search context profiles — makes the agent multi-purpose.

Instead of hardcoded cybersecurity queries, search context is loaded
from config/search_profiles.yml. The active profile is selected via
the SEARCH_PROFILE env var (default: "cybersecurity").

Multiple profiles can be activated simultaneously by comma-separating:
  SEARCH_PROFILE=cybersecurity,ai_security,cloud_infra
"""
from __future__ import annotations

from pathlib import Path

import yaml

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("search_context")

_profiles_cache: dict | None = None


def _load_all_profiles() -> dict:
    """Load all profiles from search_profiles.yml."""
    global _profiles_cache
    if _profiles_cache is not None:
        return _profiles_cache

    path = Path(settings.config_dir) / "search_profiles.yml"
    if not path.exists():
        # Fall back to legacy search_queries.yml
        legacy = Path(settings.config_dir) / "search_queries.yml"
        if legacy.exists():
            with open(legacy) as f:
                data = yaml.safe_load(f) or {}
            _profiles_cache = {
                "legacy": {
                    "description": "Legacy search queries",
                    "enabled_engines": data.get("enabled_engines", ["google_news", "bing"]),
                    "results_per_query": data.get("results_per_query", 10),
                    "queries": data.get("queries", []),
                }
            }
            log.info("search_context.legacy_loaded")
            return _profiles_cache

        _profiles_cache = {}
        return _profiles_cache

    with open(path) as f:
        _profiles_cache = yaml.safe_load(f) or {}

    log.info("search_context.profiles_loaded", count=len(_profiles_cache))
    return _profiles_cache


def reload_profiles() -> None:
    """Force reload of profiles from disk."""
    global _profiles_cache
    _profiles_cache = None
    _load_all_profiles()


def list_profiles() -> list[dict]:
    """List all available profiles with metadata."""
    profiles = _load_all_profiles()
    return [
        {
            "name": name,
            "description": p.get("description", ""),
            "queries": len(p.get("queries", [])),
            "engines": p.get("enabled_engines", []),
        }
        for name, p in profiles.items()
    ]


def get_active_profile_names() -> list[str]:
    """Get list of active profile names from settings."""
    raw = settings.search_profile
    return [p.strip() for p in raw.split(",") if p.strip()]


def get_merged_search_config() -> dict:
    """Merge all active profiles into a single search config.

    Combines queries from all active profiles, deduplicating.
    Uses the union of all enabled engines.
    Uses the max results_per_query across profiles.
    """
    all_profiles = _load_all_profiles()
    active_names = get_active_profile_names()

    merged_queries: list[str] = []
    merged_engines: set[str] = set()
    max_rpp = 10
    seen_queries: set[str] = set()

    matched = 0
    for name in active_names:
        profile = all_profiles.get(name)
        if not profile:
            log.warning("search_context.profile_not_found", name=name)
            continue

        matched += 1
        for q in profile.get("queries", []):
            q_lower = q.lower().strip()
            if q_lower not in seen_queries:
                seen_queries.add(q_lower)
                merged_queries.append(q)

        for e in profile.get("enabled_engines", []):
            merged_engines.add(e)

        rpp = profile.get("results_per_query", 10)
        if rpp > max_rpp:
            max_rpp = rpp

    if matched == 0:
        log.warning("search_context.no_active_profiles", requested=active_names)

    log.info(
        "search_context.merged",
        profiles=active_names,
        matched=matched,
        queries=len(merged_queries),
        engines=sorted(merged_engines),
    )

    return {
        "enabled_engines": sorted(merged_engines),
        "results_per_query": max_rpp,
        "queries": merged_queries,
    }
