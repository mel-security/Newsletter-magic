from __future__ import annotations

import httpx

_USER_AGENT = (
    "CyberNewsAgent/0.1 (+https://github.com/cyber-news-agent; bot)"
)

_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


def http_client(**kwargs) -> httpx.AsyncClient:
    """Return a pre-configured async HTTP client."""
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", _USER_AGENT)
    return httpx.AsyncClient(
        headers=headers,
        timeout=_TIMEOUT,
        follow_redirects=True,
        **kwargs,
    )
