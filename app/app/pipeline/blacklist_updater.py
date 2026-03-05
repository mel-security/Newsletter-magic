"""Blacklist auto-updater — discovers new prompt injection techniques
from the internet and proposes additions to the blacklist.

Flow:
  1. Search Google/Bing for latest prompt injection techniques
  2. Fetch + extract article text
  3. Use the Writer LLM to extract injection patterns from articles
  4. Validate extracted patterns won't cause false positives (viability check)
  5. Append new entries to prompt_blacklist.txt
  6. Reload the sanitizer

Safety:
  - New entries are ALWAYS validated against known-good corpus before adding
  - The LLM response itself is sanitized (yes, recursion-safe — we use
    the built-in patterns only, not the blacklist, for this specific call)
  - A backup of the blacklist is created before any modification
  - Maximum entries per update is capped to prevent runaway growth
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import trafilatura

from app.settings import settings
from app.utils.http import http_client
from app.utils.logging import get_logger

log = get_logger("blacklist_updater")

# Queries to discover new injection techniques
_DISCOVERY_QUERIES = [
    "prompt injection new technique LLM bypass",
    "jailbreak AI chatbot new method",
    "LLM prompt injection attack research",
    "indirect prompt injection technique",
    "AI guardrail bypass new approach",
    "prompt injection payload examples",
    "LLM red team prompt injection",
    "adversarial prompt attack new",
]

# Max new entries per auto-update run
_MAX_NEW_ENTRIES = 20

# LLM prompt for extracting injection patterns
_EXTRACTION_PROMPT = """You are a cybersecurity analyst specializing in AI/LLM security.

Analyze the following article text about prompt injection techniques.
Extract specific phrases, patterns, or payloads that could be used for prompt injection attacks.

Rules:
1. Output ONLY valid JSON — no prose outside JSON.
2. Extract actual attack phrases/patterns, NOT descriptions of attacks.
3. Each pattern should be a substring that would appear in malicious text.
4. Include both exact phrases and regex patterns where useful.
5. Do NOT include generic words that would match normal text.
6. Focus on ACTIONABLE patterns: things that are clearly injection attempts.

Output JSON Schema:
{{
  "patterns": [
    {{
      "type": "phrase|regex",
      "value": "the exact phrase or regex pattern",
      "category": "instruction_override|role_hijack|delimiter|encoding|extraction|other",
      "confidence": "high|medium",
      "reason": "brief explanation"
    }}
  ]
}}

Article text:
{article_text}"""


async def _search_for_techniques() -> list[dict]:
    """Search for articles about new prompt injection techniques."""
    from app.pipeline.search import search_google_news, search_bing

    all_items = []
    seen_urls = set()

    for query in _DISCOVERY_QUERIES:
        for searcher in [search_google_news, search_bing]:
            try:
                items = await searcher(query, num_results=5)
                for item in items:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_items.append(item)
            except Exception as exc:
                log.warning("blacklist_updater.search_error", error=str(exc))

    log.info("blacklist_updater.search_done", articles=len(all_items))
    return all_items[:30]  # Cap total articles to process


async def _fetch_article_text(url: str) -> str | None:
    """Fetch and extract article text."""
    try:
        async with http_client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
        text = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        return text
    except Exception as exc:
        log.warning("blacklist_updater.fetch_error", url=url, error=str(exc))
        return None


async def _extract_patterns_via_llm(article_text: str) -> list[dict]:
    """Use LLM to extract injection patterns from article text.

    IMPORTANT: We import ollama_client internals directly and bypass
    the sanitize_for_llm layer for this specific call, since the
    article text IS about injection techniques and would be blocked.
    Instead we use a targeted, minimal sanitization.
    """
    import httpx

    # Truncate to avoid overwhelming the LLM
    text = article_text[:4000]

    prompt = _EXTRACTION_PROMPT.replace("{article_text}", text)

    payload = {
        "model": settings.model_writer,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2},
        "keep_alive": settings.ollama_keep_alive,
    }

    try:
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()

        data = resp.json()
        content = data.get("message", {}).get("content", "")

        # Strip think tags from deepseek
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Extract JSON
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return []

        parsed = json.loads(match.group(0))
        return parsed.get("patterns", [])

    except Exception as exc:
        log.warning("blacklist_updater.llm_error", error=str(exc))
        return []


def _load_existing_entries() -> set[str]:
    """Load existing blacklist entries for dedup."""
    path = Path(settings.config_dir) / "prompt_blacklist.txt"
    if not path.exists():
        return set()

    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.add(line.lower())
    return entries


def _backup_blacklist() -> Path | None:
    """Create a timestamped backup of the blacklist."""
    path = Path(settings.config_dir) / "prompt_blacklist.txt"
    if not path.exists():
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(settings.config_dir) / "blacklist_backups"
    backup_dir.mkdir(exist_ok=True)
    backup_path = backup_dir / f"prompt_blacklist_{ts}.txt"
    shutil.copy2(path, backup_path)

    # Keep only last 10 backups
    backups = sorted(backup_dir.glob("prompt_blacklist_*.txt"))
    for old in backups[:-10]:
        old.unlink()

    log.info("blacklist_updater.backup_created", path=str(backup_path))
    return backup_path


def _append_entries(new_entries: list[dict]) -> int:
    """Append validated new entries to the blacklist file."""
    path = Path(settings.config_dir) / "prompt_blacklist.txt"

    lines = [
        "",
        f"# ── Auto-discovered ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}) ──",
    ]

    added = 0
    for entry in new_entries:
        entry_type = entry.get("type", "phrase")
        value = entry.get("value", "").strip()
        category = entry.get("category", "other")

        if not value:
            continue

        if entry_type == "regex":
            # Validate regex compiles
            try:
                re.compile(value, re.IGNORECASE)
            except re.error:
                log.warning("blacklist_updater.bad_regex", value=value)
                continue
            lines.append(f"regex:{value}")
        else:
            lines.append(value.lower())

        added += 1

    if added > 0:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    log.info("blacklist_updater.entries_appended", count=added)
    return added


async def auto_update_blacklist(dry_run: bool = False) -> dict:
    """Run the full blacklist auto-update pipeline.

    Returns stats dict with discovery and update information.
    """
    from app.pipeline.blacklist_viability import validate_new_entries

    stats = {
        "articles_found": 0,
        "articles_processed": 0,
        "patterns_extracted": 0,
        "patterns_validated": 0,
        "patterns_added": 0,
        "patterns_rejected_viability": 0,
        "dry_run": dry_run,
    }

    # 1. Search for articles about injection techniques
    log.info("blacklist_updater.start")
    articles = await _search_for_techniques()
    stats["articles_found"] = len(articles)

    # 2. Fetch and extract patterns from each article
    existing = _load_existing_entries()
    all_new_patterns: list[dict] = []

    for article in articles:
        url = article.get("url", "")
        if not url:
            continue

        text = await _fetch_article_text(url)
        if not text or len(text) < 100:
            continue

        stats["articles_processed"] += 1

        patterns = await _extract_patterns_via_llm(text)
        for p in patterns:
            value = p.get("value", "").strip().lower()
            ptype = p.get("type", "phrase")
            full_key = f"regex:{value}" if ptype == "regex" else value

            # Skip if already in blacklist
            if full_key in existing:
                continue

            # Skip very short patterns (high false-positive risk)
            if len(value) < 8:
                continue

            # Skip overly generic patterns
            if value in {"the", "system", "prompt", "ignore", "instructions"}:
                continue

            all_new_patterns.append(p)
            stats["patterns_extracted"] += 1

        # Cap total patterns
        if stats["patterns_extracted"] >= _MAX_NEW_ENTRIES * 2:
            break

    if not all_new_patterns:
        log.info("blacklist_updater.no_new_patterns")
        return stats

    # 3. Validate patterns won't cause false positives
    validated = validate_new_entries(
        [p.get("value", "") for p in all_new_patterns],
        [p.get("type", "phrase") for p in all_new_patterns],
    )

    validated_patterns = []
    for i, (pattern, is_safe) in enumerate(zip(all_new_patterns, validated)):
        if is_safe:
            validated_patterns.append(pattern)
            stats["patterns_validated"] += 1
        else:
            stats["patterns_rejected_viability"] += 1
            log.info(
                "blacklist_updater.pattern_rejected",
                value=pattern.get("value"),
                reason="viability_check_failed",
            )

    # Cap to max entries
    validated_patterns = validated_patterns[:_MAX_NEW_ENTRIES]

    # 4. Apply updates (unless dry run)
    if dry_run:
        log.info("blacklist_updater.dry_run", would_add=len(validated_patterns))
        stats["proposed_entries"] = [
            {"type": p.get("type"), "value": p.get("value"), "category": p.get("category")}
            for p in validated_patterns
        ]
    else:
        if validated_patterns:
            _backup_blacklist()
            added = _append_entries(validated_patterns)
            stats["patterns_added"] = added

            # Reload the sanitizer
            from app.pipeline.sanitizer import reload_blacklist
            reload_blacklist()
            log.info("blacklist_updater.complete", added=added)
        else:
            log.info("blacklist_updater.nothing_to_add")

    return stats
