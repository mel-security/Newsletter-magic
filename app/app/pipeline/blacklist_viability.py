"""Blacklist viability checker — prevents self-lockdown from collisions.

Problem: If the blacklist contains entries that match normal cybersecurity
text (e.g., "system prompt" in an article *about* system prompts), the
sanitizer will reject legitimate content, effectively locking down the bot.

This module:
  1. Maintains a corpus of known-good text samples (cybersecurity articles,
     newsletter fragments, normal technical writing).
  2. Tests every blacklist entry against this corpus.
  3. Flags entries that cause false positives (match normal content).
  4. Can run as a pre-flight check before the pipeline starts.
  5. Validates NEW entries before they're added (used by blacklist_updater).

Collision types:
  - HARD collision: a phrase that appears verbatim in >50% of good samples
    → entry should be REMOVED (would block most legitimate content)
  - SOFT collision: a phrase that appears in 10-50% of good samples
    → entry should be reviewed / made more specific
  - SAFE: phrase appears in <10% of good samples → entry is viable
"""
from __future__ import annotations

import re
from pathlib import Path

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("blacklist_viability")

# ── Known-good corpus ─────────────────────────────────────
# Representative text samples that should NEVER be blocked.
# These cover normal cybersecurity reporting, technical docs,
# newsletter text, and general tech writing.

_GOOD_CORPUS: list[str] = [
    # Normal CVE reporting
    "A critical vulnerability CVE-2024-1234 was discovered in Apache HTTP Server. "
    "The flaw allows remote code execution via crafted HTTP requests. CISA has added "
    "this to the Known Exploited Vulnerabilities catalog. Organizations should patch immediately.",

    # Normal threat intelligence
    "The APT group Midnight Blizzard has been observed targeting government agencies "
    "using spear-phishing emails containing malicious attachments. The campaign leverages "
    "a new backdoor that communicates over encrypted DNS channels.",

    # Normal ransomware reporting
    "LockBit ransomware operators have claimed responsibility for attacking a major "
    "healthcare provider. The data breach exposed patient records of 2.3 million individuals. "
    "The group is demanding a $10 million ransom payment in Bitcoin.",

    # Article discussing prompt injection (legitimate security research)
    "Researchers at ETH Zurich published a paper analyzing indirect prompt injection "
    "attacks against large language models. The study found that current defenses are "
    "insufficient against sophisticated multi-step injection chains.",

    # Normal CERT advisory
    "CERT-FR a publié un avis de sécurité concernant une vulnérabilité critique dans "
    "Microsoft Exchange Server. L'exploitation de cette faille permet une élévation de "
    "privilèges. Il est recommandé d'appliquer le correctif sans délai.",

    # Normal newsletter section
    "This week's top stories include a zero-day in Chrome's V8 engine, a new variant "
    "of the Emotet botnet, and CISA's updated guidance on securing cloud infrastructure. "
    "The CVSS score for the Chrome vulnerability is 9.8.",

    # Technical documentation
    "The system architecture uses a microservices pattern with API gateway authentication. "
    "Each service communicates over mTLS. The database layer implements role-based access "
    "control with encrypted credentials stored in HashiCorp Vault.",

    # Incident response report
    "The incident response team identified the initial access vector as a compromised "
    "VPN credential. The attacker performed lateral movement using PsExec and extracted "
    "sensitive data to an external server over port 443.",

    # AI security research (legitimate discussion)
    "The paper demonstrates how adversarial prompts can cause language models to deviate "
    "from their intended behavior. The authors propose a new defense mechanism based on "
    "input preprocessing and output validation.",

    # Normal IoT security
    "Multiple vulnerabilities were found in popular smart home devices from three vendors. "
    "The flaws include hardcoded credentials, unencrypted firmware updates, and buffer "
    "overflow conditions in the web management interface.",

    # Cloud security report
    "An S3 bucket misconfiguration at a Fortune 500 company exposed 50GB of internal "
    "documents including API keys and database connection strings. The bucket was publicly "
    "accessible for approximately 6 months before discovery.",

    # Patch management article
    "Microsoft's Patch Tuesday release addresses 87 vulnerabilities, including 6 critical "
    "remote code execution flaws. System administrators should prioritize patching the "
    "Exchange Server and Windows kernel vulnerabilities.",

    # General technical writing about LLMs
    "Large language models process instructions through a system prompt that defines their "
    "behavior and constraints. The model generates responses based on the context window "
    "which includes both system-level and user-level messages.",

    # Security tool documentation
    "Configure the firewall rules to allow inbound traffic on port 443 for HTTPS. "
    "The intrusion detection system should be set to monitor for SQL injection patterns "
    "and cross-site scripting attempts in web application traffic.",

    # French cybersecurity article
    "Une nouvelle campagne de phishing cible les entreprises françaises du secteur bancaire. "
    "Les attaquants utilisent des techniques d'ingénierie sociale sophistiquées pour voler "
    "les identifiants de connexion des employés.",
]


def _test_phrase_against_corpus(phrase: str, corpus: list[str] | None = None) -> dict:
    """Test a single phrase against the known-good corpus.

    Returns dict with collision analysis.
    """
    corpus = corpus or _GOOD_CORPUS
    phrase_lower = phrase.lower()
    total = len(corpus)
    matches = 0
    match_samples = []

    for i, sample in enumerate(corpus):
        if phrase_lower in sample.lower():
            matches += 1
            # Store which sample matched (truncated)
            match_samples.append(f"sample[{i}]: ...{sample[max(0, sample.lower().find(phrase_lower) - 30):sample.lower().find(phrase_lower) + len(phrase_lower) + 30]}...")

    ratio = matches / total if total > 0 else 0

    if ratio > 0.5:
        severity = "hard_collision"
    elif ratio > 0.1:
        severity = "soft_collision"
    else:
        severity = "safe"

    return {
        "phrase": phrase,
        "matches": matches,
        "total_samples": total,
        "ratio": round(ratio, 3),
        "severity": severity,
        "match_samples": match_samples[:3],
    }


def _test_regex_against_corpus(pattern_str: str, corpus: list[str] | None = None) -> dict:
    """Test a regex pattern against the known-good corpus."""
    corpus = corpus or _GOOD_CORPUS
    total = len(corpus)
    matches = 0
    match_samples = []

    try:
        pattern = re.compile(pattern_str, re.IGNORECASE)
    except re.error as exc:
        return {
            "pattern": pattern_str,
            "error": f"Invalid regex: {exc}",
            "severity": "error",
            "matches": 0,
            "total_samples": total,
            "ratio": 0,
        }

    for i, sample in enumerate(corpus):
        m = pattern.search(sample)
        if m:
            matches += 1
            match_samples.append(f"sample[{i}]: matched '{m.group()}'")

    ratio = matches / total if total > 0 else 0

    if ratio > 0.5:
        severity = "hard_collision"
    elif ratio > 0.1:
        severity = "soft_collision"
    else:
        severity = "safe"

    return {
        "pattern": pattern_str,
        "matches": matches,
        "total_samples": total,
        "ratio": round(ratio, 3),
        "severity": severity,
        "match_samples": match_samples[:3],
    }


def validate_new_entries(
    values: list[str],
    types: list[str],
    corpus: list[str] | None = None,
) -> list[bool]:
    """Validate a batch of proposed new entries against the corpus.

    Args:
        values: List of phrase/regex values to test.
        types: Corresponding list of types ("phrase" or "regex").
        corpus: Optional custom corpus (defaults to built-in).

    Returns:
        List of booleans — True if the entry is safe to add, False if it
        would cause collisions.
    """
    results = []

    for value, entry_type in zip(values, types):
        if entry_type == "regex":
            report = _test_regex_against_corpus(value, corpus)
        else:
            report = _test_phrase_against_corpus(value, corpus)

        is_safe = report["severity"] == "safe"

        if not is_safe:
            log.warning(
                "blacklist_viability.collision",
                value=value,
                type=entry_type,
                severity=report["severity"],
                ratio=report["ratio"],
                matches=report["matches"],
            )

        results.append(is_safe)

    return results


def audit_blacklist(custom_corpus: list[str] | None = None) -> dict:
    """Full audit of the current blacklist against the known-good corpus.

    Returns a report with all entries categorized by collision severity.
    """
    path = Path(settings.config_dir) / "prompt_blacklist.txt"
    if not path.exists():
        return {"error": "Blacklist file not found", "entries": 0}

    report = {
        "entries_checked": 0,
        "safe": 0,
        "soft_collisions": [],
        "hard_collisions": [],
        "errors": [],
        "recommendations": [],
    }

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        report["entries_checked"] += 1

        if line.startswith("regex:"):
            pattern_str = line[6:].strip()
            result = _test_regex_against_corpus(pattern_str, custom_corpus)
            result["raw_line"] = line
        else:
            result = _test_phrase_against_corpus(line, custom_corpus)
            result["raw_line"] = line

        if result.get("severity") == "error":
            report["errors"].append(result)
        elif result["severity"] == "hard_collision":
            report["hard_collisions"].append(result)
        elif result["severity"] == "soft_collision":
            report["soft_collisions"].append(result)
        else:
            report["safe"] += 1

    # Generate recommendations
    if report["hard_collisions"]:
        report["recommendations"].append(
            f"CRITICAL: {len(report['hard_collisions'])} entries match >50% of normal "
            f"content. These will block legitimate articles. Remove or refine them."
        )
        for collision in report["hard_collisions"]:
            raw = collision.get("raw_line", collision.get("phrase", collision.get("pattern", "")))
            report["recommendations"].append(
                f"  REMOVE or REFINE: '{raw}' (matches {collision['matches']}/{collision['total_samples']} samples)"
            )

    if report["soft_collisions"]:
        report["recommendations"].append(
            f"WARNING: {len(report['soft_collisions'])} entries match 10-50% of normal "
            f"content. Consider making these more specific."
        )

    if report["errors"]:
        report["recommendations"].append(
            f"FIX: {len(report['errors'])} entries have invalid regex patterns."
        )

    if not report["hard_collisions"] and not report["soft_collisions"] and not report["errors"]:
        report["recommendations"].append("All entries are viable. No collisions detected.")

    log.info(
        "blacklist_viability.audit_complete",
        entries=report["entries_checked"],
        safe=report["safe"],
        soft=len(report["soft_collisions"]),
        hard=len(report["hard_collisions"]),
        errors=len(report["errors"]),
    )

    return report


def auto_fix_collisions(dry_run: bool = True) -> dict:
    """Automatically fix hard collisions by commenting them out.

    Soft collisions are left for manual review.
    Only runs if dry_run=False.
    """
    path = Path(settings.config_dir) / "prompt_blacklist.txt"
    if not path.exists():
        return {"error": "Blacklist file not found"}

    audit = audit_blacklist()
    hard_lines = {c.get("raw_line", "") for c in audit.get("hard_collisions", [])}

    if not hard_lines:
        return {"fixed": 0, "message": "No hard collisions to fix."}

    if dry_run:
        return {
            "dry_run": True,
            "would_disable": list(hard_lines),
            "count": len(hard_lines),
        }

    # Backup first
    import shutil
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(settings.config_dir) / "blacklist_backups"
    backup_dir.mkdir(exist_ok=True)
    shutil.copy2(path, backup_dir / f"prompt_blacklist_prefix_{ts}.txt")

    # Rewrite file with hard collisions commented out
    original = path.read_text(encoding="utf-8")
    new_lines = []
    fixed = 0

    for line in original.splitlines():
        stripped = line.strip()
        if stripped in hard_lines:
            new_lines.append(f"# DISABLED (hard collision): {line}")
            fixed += 1
        else:
            new_lines.append(line)

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Reload sanitizer
    from app.pipeline.sanitizer import reload_blacklist
    reload_blacklist()

    log.info("blacklist_viability.auto_fix", fixed=fixed)
    return {"fixed": fixed, "disabled_entries": list(hard_lines)}
