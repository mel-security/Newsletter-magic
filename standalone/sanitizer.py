"""Standalone prompt injection sanitizer — lightweight version."""
from __future__ import annotations

import re

# ── Built-in patterns (always active) ──────────────────────────

_BUILTIN_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|context)",
        r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|context)",
        r"override\s+(all\s+)?(previous|prior|system)\s+(instructions?|prompts?|rules?)",
        r"you\s+are\s+now\s+(a|an|the)\s+",
        r"act\s+as\s+(a|an|the)\s+",
        r"pretend\s+(you\s+are|to\s+be)\s+",
        r"new\s+(instructions?|role|persona|identity)\s*[:\-]",
        r"system\s*prompt\s*[:\-]",
        r"\[system\]",
        r"\[inst\]",
        r"<\s*/?\s*system\s*>",
        r"<<\s*SYS\s*>>",
        r"end.?of.?prompt",
        r"begin.?new.?conversation",
        r"reset\s+(your\s+)?(context|memory|instructions?)",
        r"do\s+not\s+follow\s+(any|your)\s+(previous|prior)",
        r"stop\s+(all\s+)?instruction",
        r"ign[o0]re\s+all\s+instruct[i1][o0]ns",
        r"jailbreak",
        r"DAN\s+mode",
    ]
]


def sanitize_text(text: str, source: str = "unknown", strict: bool = False) -> tuple[str, dict]:
    """Sanitize text against prompt injection.

    Returns (cleaned_text, report_dict).
    If injection detected: returns ("", report) with blocked=True.
    """
    if not text or not text.strip():
        return ("", {"blocked": False, "source": source, "reason": "empty"})

    for pattern in _BUILTIN_PATTERNS:
        if pattern.search(text):
            return ("", {
                "blocked": True,
                "source": source,
                "reason": f"builtin_pattern: {pattern.pattern[:60]}",
            })

    return (text.strip(), {"blocked": False, "source": source})
