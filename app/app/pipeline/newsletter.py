"""Devil Twins orchestration — Writer + Critic LLM pipeline."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article, IOC, Story, Vuln
from app.llm.ollama_client import chat_json
from app.llm.schemas import CriticOutput, WriterOutput
from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("newsletter")


def _load_prompt(name: str) -> str:
    path = Path(settings.config_dir) / "prompts" / f"{name}.md"
    return path.read_text()


def build_context_pack(session: Session) -> dict:
    """Build context pack from DB: top stories, vulns, IOCs."""
    stories = session.execute(
        select(Story).order_by(Story.last_seen.desc()).limit(settings.max_stories)
    ).scalars().all()

    story_data = []
    for story in stories:
        articles = session.execute(
            select(Article)
            .where(Article.story_id == story.id)
            .order_by(Article.score.desc())
        ).scalars().all()

        story_data.append({
            "title": story.canonical_title,
            "severity": story.severity,
            "summary": story.summary[:300] if story.summary else "",
            "articles": [
                {"title": a.title, "url": a.url, "source": a.source, "score": a.score}
                for a in articles[:5]
            ],
        })

    vulns = session.execute(
        select(Vuln).order_by(Vuln.id.desc()).limit(20)
    ).scalars().all()

    vuln_data = [
        {
            "cve": v.cve,
            "severity": v.severity,
            "exploited": v.exploited_bool,
            "references": v.references or [],
        }
        for v in vulns
    ]

    iocs = session.execute(
        select(IOC).order_by(IOC.first_seen.desc()).limit(30)
    ).scalars().all()

    ioc_data = [
        {
            "type": i.type,
            "value": i.value,
            "confidence": i.confidence,
            "context": i.context or "",
            "sources": i.sources or [],
        }
        for i in iocs
    ]

    return {
        "date": date.today().isoformat(),
        "lang": settings.lang,
        "stories": story_data,
        "vulns": vuln_data,
        "iocs": ioc_data,
    }


def build_fallback_digest(context_pack: dict) -> dict:
    """Generate a safe fallback digest (list + links, no LLM claims)."""
    sections = []
    stories_list = []

    for story in context_pack.get("stories", []):
        sources = [a["url"] for a in story.get("articles", []) if a.get("url")]
        stories_list.append({
            "headline": story["title"],
            "severity": story.get("severity", "medium"),
            "summary": story.get("summary", "")[:200],
            "cves": [],
            "iocs": [],
            "sources": sources[:3],
            "recommendations": None,
        })

    if stories_list:
        sections.append({
            "section_title": "Digest" if context_pack.get("lang") != "fr" else "Résumé",
            "stories": stories_list[:settings.max_stories],
        })

    ioc_table = [
        {
            "type": i["type"],
            "value": i["value"],
            "context": i.get("context", ""),
            "sources": i.get("sources", []),
        }
        for i in context_pack.get("iocs", [])[:15]
    ]

    return {
        "newsletter": {
            "date": context_pack["date"],
            "lang": context_pack.get("lang", "en"),
            "title": f"Cyber Security Digest — {context_pack['date']}",
            "intro": "Automated digest — safe mode (no AI-generated claims).",
            "sections": sections,
            "ioc_table": ioc_table,
            "closing": "Stay vigilant. Verify all indicators independently.",
        }
    }


async def generate_newsletter(session: Session) -> tuple[dict, bool]:
    """Run the Devil Twins pipeline. Returns (newsletter_dict, is_fallback)."""
    context_pack = build_context_pack(session)

    if not context_pack["stories"]:
        log.warning("newsletter.no_stories")
        return build_fallback_digest(context_pack), True

    context_json = json.dumps(context_pack, indent=2, default=str)

    # ── Step 1: Writer generates v1 ──────────────────────
    writer_prompt_template = _load_prompt("writer")
    writer_prompt = writer_prompt_template.replace("{context_pack}", context_json)

    log.info("newsletter.writer_v1.start")
    try:
        v1_raw = await chat_json(
            model=settings.model_writer,
            prompt=writer_prompt,
            temperature=0.4,
        )
        v1 = WriterOutput.model_validate(v1_raw)
        log.info("newsletter.writer_v1.ok")
    except (ValueError, ValidationError) as exc:
        log.error("newsletter.writer_v1.fail", error=str(exc))
        return build_fallback_digest(context_pack), True

    # ── Step 2: Critic reviews v1 ────────────────────────
    critic_prompt_template = _load_prompt("critic")
    critic_prompt = (
        critic_prompt_template
        .replace("{newsletter_draft}", json.dumps(v1_raw, indent=2, default=str))
        .replace("{context_pack}", context_json)
    )

    log.info("newsletter.critic_v1.start")
    try:
        review_raw = await chat_json(
            model=settings.model_critic,
            prompt=critic_prompt,
            temperature=0.2,
        )
        review = CriticOutput.model_validate(review_raw)
        log.info("newsletter.critic_v1.ok", verdict=review.review.verdict, score=review.review.score)
    except (ValueError, ValidationError) as exc:
        log.error("newsletter.critic_v1.fail", error=str(exc))
        return build_fallback_digest(context_pack), True

    # If critic passes v1, use it
    if review.review.verdict == "PASS":
        log.info("newsletter.v1_accepted")
        return v1_raw, False

    # ── Step 3: Writer revises to v2 using patches ───────
    patches_json = json.dumps(
        {"patches": [p.model_dump() for p in review.review.patches],
         "issues": [i.model_dump() for i in review.review.issues]},
        indent=2,
    )
    revision_prompt = (
        f"Revise the newsletter based on the critic's feedback.\n\n"
        f"Original draft:\n{json.dumps(v1_raw, indent=2, default=str)}\n\n"
        f"Critic feedback and patches:\n{patches_json}\n\n"
        f"Context pack:\n{context_json}\n\n"
        f"Output ONLY the revised newsletter JSON following the same schema."
    )

    log.info("newsletter.writer_v2.start")
    try:
        v2_raw = await chat_json(
            model=settings.model_writer,
            prompt=revision_prompt,
            temperature=0.3,
        )
        v2 = WriterOutput.model_validate(v2_raw)
        log.info("newsletter.writer_v2.ok")
    except (ValueError, ValidationError) as exc:
        log.error("newsletter.writer_v2.fail", error=str(exc))
        return build_fallback_digest(context_pack), True

    # ── Step 4: Critic verifies v2 ───────────────────────
    verify_prompt = (
        critic_prompt_template
        .replace("{newsletter_draft}", json.dumps(v2_raw, indent=2, default=str))
        .replace("{context_pack}", context_json)
    )

    log.info("newsletter.critic_v2.start")
    try:
        review2_raw = await chat_json(
            model=settings.model_critic,
            prompt=verify_prompt,
            temperature=0.2,
        )
        review2 = CriticOutput.model_validate(review2_raw)
        log.info("newsletter.critic_v2.ok", verdict=review2.review.verdict, score=review2.review.score)
    except (ValueError, ValidationError) as exc:
        log.error("newsletter.critic_v2.fail", error=str(exc))
        return build_fallback_digest(context_pack), True

    if review2.review.verdict == "PASS":
        log.info("newsletter.v2_accepted")
        return v2_raw, False

    # ── Step 5: Fallback ─────────────────────────────────
    log.warning("newsletter.fallback", reason="critic rejected v2")
    return build_fallback_digest(context_pack), True
