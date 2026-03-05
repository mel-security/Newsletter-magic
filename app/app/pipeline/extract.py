"""Extract IOCs and CVEs from article text using regex."""
from __future__ import annotations

import ipaddress
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article, IOC, Vuln
from app.utils.logging import get_logger

log = get_logger("extract")

# ── IOC patterns ─────────────────────────────────────────
RE_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
RE_DOMAIN = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|net|org|io|info|biz|xyz|top|ru|cn|tk|ml|ga|cf|de|uk|fr|nl|cc|pw|onion)\b"
)
RE_URL = re.compile(
    r"https?://[^\s<>\"'\)\]}{,]+"
)
RE_SHA256 = re.compile(r"\b[a-fA-F0-9]{64}\b")
RE_SHA1 = re.compile(r"\b[a-fA-F0-9]{40}\b")
RE_MD5 = re.compile(r"\b[a-fA-F0-9]{32}\b")

# ── CVE pattern ──────────────────────────────────────────
RE_CVE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)

# Known false-positive IPs to skip
_BOGON_PREFIXES = ("0.", "10.", "127.", "169.254.", "172.16.", "192.168.", "255.")


def _is_valid_ip(ip: str) -> bool:
    """Check if IP is valid and not a private/bogon address."""
    if any(ip.startswith(p) for p in _BOGON_PREFIXES):
        return False
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_global
    except ValueError:
        return False


def _get_context(text: str, match_start: int, window: int = 80) -> str:
    """Get surrounding context for a match."""
    start = max(0, match_start - window)
    end = min(len(text), match_start + window)
    return text[start:end].replace("\n", " ").strip()


def extract_iocs_from_text(text: str) -> list[dict]:
    """Extract IOCs from text using regex patterns."""
    iocs = []
    seen = set()

    # IPv4
    for m in RE_IPV4.finditer(text):
        val = m.group()
        if val not in seen and _is_valid_ip(val):
            seen.add(val)
            iocs.append({
                "type": "ipv4",
                "value": val,
                "confidence": "high",
                "context": _get_context(text, m.start()),
            })

    # Domains (exclude common non-IOC domains)
    skip_domains = {"example.com", "github.com", "google.com", "microsoft.com", "twitter.com"}
    for m in RE_DOMAIN.finditer(text):
        val = m.group().lower()
        if val not in seen and val not in skip_domains:
            seen.add(val)
            iocs.append({
                "type": "domain",
                "value": val,
                "confidence": "medium",
                "context": _get_context(text, m.start()),
            })

    # SHA-256
    for m in RE_SHA256.finditer(text):
        val = m.group().lower()
        if val not in seen:
            seen.add(val)
            iocs.append({
                "type": "sha256",
                "value": val,
                "confidence": "high",
                "context": _get_context(text, m.start()),
            })

    # MD5 (only if not already matched as part of sha256/sha1)
    for m in RE_MD5.finditer(text):
        val = m.group().lower()
        if val not in seen:
            seen.add(val)
            iocs.append({
                "type": "md5",
                "value": val,
                "confidence": "medium",
                "context": _get_context(text, m.start()),
            })

    return iocs


def extract_cves_from_text(text: str) -> list[str]:
    """Extract unique CVE identifiers from text."""
    cves = set()
    for m in RE_CVE.finditer(text):
        cves.add(m.group().upper())
    return sorted(cves)


def extract_all(session: Session) -> dict:
    """Extract IOCs and CVEs from all unprocessed articles."""
    stats = {"articles": 0, "iocs": 0, "cves": 0}

    articles = session.execute(
        select(Article).where(Article.score == 0).where(Article.text.isnot(None))
    ).scalars().all()

    for article in articles:
        stats["articles"] += 1

        # Extract IOCs
        ioc_dicts = extract_iocs_from_text(article.text)
        for ioc_d in ioc_dicts:
            existing = session.execute(
                select(IOC).where(IOC.value == ioc_d["value"])
            ).scalar_one_or_none()

            if not existing:
                ioc = IOC(
                    type=ioc_d["type"],
                    value=ioc_d["value"],
                    confidence=ioc_d["confidence"],
                    context=ioc_d["context"],
                    sources=[article.url],
                )
                session.add(ioc)
                stats["iocs"] += 1
            else:
                # Update sources list
                if existing.sources and article.url not in existing.sources:
                    existing.sources = existing.sources + [article.url]

        # Extract CVEs
        cves = extract_cves_from_text(article.text)
        for cve_id in cves:
            existing = session.execute(
                select(Vuln).where(Vuln.cve == cve_id)
            ).scalar_one_or_none()

            if not existing:
                vuln = Vuln(
                    cve=cve_id,
                    severity=None,
                    exploited_bool=False,
                    references=[article.url],
                )
                session.add(vuln)
                stats["cves"] += 1
            else:
                if existing.references and article.url not in existing.references:
                    existing.references = existing.references + [article.url]

    session.commit()
    log.info("extract.complete", **stats)
    return stats
