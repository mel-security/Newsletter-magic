"""Content sanitizer — prompt injection defense for untrusted text.

This module acts as a proxy-cleaning layer between raw internet content
and the LLM pipeline. It strips, neutralizes, or flags text that could
be used for prompt injection attacks.

All text fetched from the internet MUST pass through sanitize_text()
before being stored in the DB or sent to any LLM.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("sanitizer")

# ── Blacklist loading ─────────────────────────────────────

_blacklist_cache: list[str] | None = None
_blacklist_regex_cache: list[re.Pattern] | None = None


def _load_blacklist() -> list[str]:
    """Load blacklist phrases from config/prompt_blacklist.txt."""
    global _blacklist_cache
    if _blacklist_cache is not None:
        return _blacklist_cache

    path = Path(settings.config_dir) / "prompt_blacklist.txt"
    if not path.exists():
        log.warning("sanitizer.no_blacklist", path=str(path))
        _blacklist_cache = []
        return _blacklist_cache

    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line.lower())

    _blacklist_cache = lines
    log.info("sanitizer.blacklist_loaded", entries=len(lines))
    return _blacklist_cache


def _load_blacklist_regexes() -> list[re.Pattern]:
    """Compile blacklist entries that start with 'regex:' as regex patterns."""
    global _blacklist_regex_cache
    if _blacklist_regex_cache is not None:
        return _blacklist_regex_cache

    patterns = []
    path = Path(settings.config_dir) / "prompt_blacklist.txt"
    if not path.exists():
        _blacklist_regex_cache = []
        return _blacklist_regex_cache

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("regex:"):
            pattern_str = line[6:].strip()
            try:
                patterns.append(re.compile(pattern_str, re.IGNORECASE))
            except re.error as exc:
                log.warning("sanitizer.bad_regex", pattern=pattern_str, error=str(exc))

    _blacklist_regex_cache = patterns
    log.info("sanitizer.regexes_loaded", count=len(patterns))
    return _blacklist_regex_cache


def reload_blacklist() -> None:
    """Force reload of blacklist (useful after config changes)."""
    global _blacklist_cache, _blacklist_regex_cache
    _blacklist_cache = None
    _blacklist_regex_cache = None
    _load_blacklist()
    _load_blacklist_regexes()


# ── Built-in injection patterns ───────────────────────────
# These are always active regardless of blacklist file.

_BUILTIN_PATTERNS: list[re.Pattern] = [
    # Direct instruction override attempts
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|context)", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"forget\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"stop\s+all\s+instruction", re.I),
    re.compile(r"override\s+(system|safety|content)\s*(prompt|filter|instruction|policy)", re.I),
    re.compile(r"new\s+instructions?\s*:", re.I),

    # Role hijacking
    re.compile(r"you\s+are\s+now\s+(?:a\s+)?(?:different|new|my)\s+(?:AI|assistant|bot|model)", re.I),
    re.compile(r"act\s+as\s+(?:if\s+)?(?:you\s+are\s+)?(?:a\s+)?(?:different|new)\s+(?:AI|assistant|bot)", re.I),
    re.compile(r"pretend\s+(?:to\s+be|you\s+are)\s+(?:a\s+)?(?:different|unrestricted|jailbroken)", re.I),
    re.compile(r"enter\s+(?:DAN|developer|debug|admin|god)\s*mode", re.I),
    re.compile(r"switch\s+to\s+(?:unrestricted|unfiltered|unlimited|jailbreak)\s*mode", re.I),

    # System prompt extraction
    re.compile(r"(?:show|reveal|display|print|output|repeat)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?|rules?)", re.I),
    re.compile(r"what\s+(?:are|is)\s+your\s+(?:system\s+)?(?:prompt|instructions?|rules?|guidelines?)", re.I),

    # Delimiter injection
    re.compile(r"<\s*/?\s*(?:system|instruction|prompt|context|role|message)\s*>", re.I),
    re.compile(r"\[\s*(?:SYSTEM|INST|INSTRUCTION|PROMPT)\s*\]", re.I),
    re.compile(r"<<\s*(?:SYS|SYSTEM|INST)\s*>>", re.I),
    re.compile(r"###\s*(?:SYSTEM|INSTRUCTION|NEW PROMPT|OVERRIDE)", re.I),

    # Encoding/obfuscation attempts
    re.compile(r"(?:base64|rot13|hex)\s*(?:decode|encrypt|encode)\s*(?:this|the following)", re.I),
    re.compile(r"(?:translate|convert)\s+(?:from\s+)?(?:base64|hex|binary|rot13)", re.I),

    # Prompt leaking via completion
    re.compile(r"complete\s+(?:the|this)\s+(?:sentence|prompt|instruction)", re.I),
    re.compile(r"continue\s+(?:from|after)\s+(?:the\s+)?(?:system|hidden)\s+(?:prompt|text)", re.I),
]


# ── Core sanitization ────────────────────────────────────

def check_blacklist(text: str) -> list[str]:
    """Check text against blacklist. Returns list of matched phrases."""
    text_lower = text.lower()
    matches = []

    # Check plain text entries
    for phrase in _load_blacklist():
        if not phrase.startswith("regex:") and phrase in text_lower:
            matches.append(phrase)

    # Check regex entries from blacklist
    for pattern in _load_blacklist_regexes():
        if pattern.search(text):
            matches.append(f"regex:{pattern.pattern}")

    return matches


def check_builtin_patterns(text: str) -> list[str]:
    """Check text against built-in injection patterns."""
    matches = []
    for pattern in _BUILTIN_PATTERNS:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return matches


def strip_injection_markers(text: str) -> str:
    """Remove common injection delimiters and markers from text."""
    # Remove XML-style role/system tags
    text = re.sub(r"<\s*/?\s*(?:system|instruction|prompt|context|role|message|s|human|assistant)\s*>", "", text, flags=re.I)

    # Remove markdown-style instruction blocks
    text = re.sub(r"###\s*(?:SYSTEM|INSTRUCTION|NEW PROMPT|OVERRIDE)[^\n]*\n?", "", text, flags=re.I)

    # Remove bracket-style markers
    text = re.sub(r"\[\s*(?:SYSTEM|INST|INSTRUCTION|PROMPT)\s*\]", "", text, flags=re.I)

    # Remove <<SYS>> style markers
    text = re.sub(r"<<\s*/?\s*(?:SYS|SYSTEM|INST)\s*>>", "", text, flags=re.I)

    return text


def sanitize_text(
    text: str,
    source: str = "unknown",
    strict: bool = True,
) -> tuple[str, dict]:
    """Sanitize untrusted text before DB storage or LLM processing.

    Args:
        text: Raw text from internet source.
        source: Source identifier for logging.
        strict: If True, reject text with any injection match.
                If False, strip markers and log warnings.

    Returns:
        Tuple of (cleaned_text, report_dict).
        If text is rejected, cleaned_text will be empty string.
    """
    report = {
        "source": source,
        "original_length": len(text),
        "blacklist_matches": [],
        "builtin_matches": [],
        "action": "pass",
        "stripped_markers": False,
    }

    if not text:
        return text, report

    # Step 1: Check built-in patterns
    builtin_hits = check_builtin_patterns(text)
    report["builtin_matches"] = builtin_hits

    # Step 2: Check blacklist
    blacklist_hits = check_blacklist(text)
    report["blacklist_matches"] = blacklist_hits

    all_hits = builtin_hits + blacklist_hits

    if all_hits:
        log.warning(
            "sanitizer.injection_detected",
            source=source,
            builtin_hits=len(builtin_hits),
            blacklist_hits=len(blacklist_hits),
            sample_matches=all_hits[:5],
        )

        if strict:
            report["action"] = "rejected"
            return "", report

    # Step 3: Strip injection markers even if no full match
    cleaned = strip_injection_markers(text)
    if cleaned != text:
        report["stripped_markers"] = True
        log.info("sanitizer.markers_stripped", source=source)

    # Step 4: Truncate extremely long text (potential resource abuse)
    max_length = 100_000  # 100K chars should be enough for any article
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
        log.warning("sanitizer.truncated", source=source, original_len=len(text))

    report["action"] = "cleaned" if report["stripped_markers"] else "pass"
    report["cleaned_length"] = len(cleaned)

    return cleaned, report


def sanitize_feed_item(item: dict, source: str = "unknown") -> tuple[dict, dict]:
    """Sanitize all text fields in a feed item dict.

    Returns (sanitized_item, combined_report).
    """
    combined_report = {"fields": {}, "rejected": False}

    for field in ("title", "summary", "content", "description"):
        if field in item and isinstance(item[field], str):
            cleaned, report = sanitize_text(item[field], source=f"{source}/{field}")
            item[field] = cleaned
            combined_report["fields"][field] = report
            if report["action"] == "rejected":
                combined_report["rejected"] = True

    return item, combined_report


def sanitize_for_llm(text: str, context_label: str = "llm_input") -> str:
    """Final sanitization pass right before sending text to LLM.

    This is more aggressive — wraps the content in clear delimiters
    so the LLM knows it's data, not instructions.
    """
    # Run standard sanitization
    cleaned, report = sanitize_text(text, source=context_label, strict=True)

    if report["action"] == "rejected":
        log.error("sanitizer.llm_input_rejected", context=context_label)
        return "[CONTENT REDACTED: potential prompt injection detected]"

    return cleaned
