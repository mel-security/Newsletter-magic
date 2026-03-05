from __future__ import annotations

import hashlib
import re
from urllib.parse import urldefrag, urlparse, urlunparse


def canonicalize_url(url: str) -> str:
    """Normalize a URL for deduplication."""
    parsed = urlparse(url.strip())
    # Remove fragment
    defragged, _ = urldefrag(urlunparse(parsed))
    # Lowercase scheme and host
    parsed2 = urlparse(defragged)
    canonical = urlunparse((
        parsed2.scheme.lower(),
        parsed2.netloc.lower(),
        parsed2.path.rstrip("/") or "/",
        parsed2.params,
        parsed2.query,
        "",
    ))
    return canonical


def content_hash(text: str) -> str:
    """SHA-256 hash of normalized text content."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def truncate(text: str, max_len: int = 500) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
