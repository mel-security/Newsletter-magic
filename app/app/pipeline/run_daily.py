"""Daily pipeline orchestrator — Celery task + CLI entry point."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone

from app.celery_app import app as celery_app
from app.db.models import Run
from app.db.session import get_sync_session
from app.utils.logging import get_logger, setup_logging

log = get_logger("pipeline")


async def _run_pipeline(dry_run: bool = False) -> dict:
    """Execute the full pipeline asynchronously."""
    from app.pipeline.ingest import ingest_sources
    from app.pipeline.normalize import normalize_raw_items
    from app.pipeline.dedup import deduplicate_articles
    from app.pipeline.extract import extract_all
    from app.pipeline.score import score_articles
    from app.pipeline.cluster import cluster_into_stories
    from app.pipeline.newsletter import generate_newsletter
    from app.pipeline.render import render_newsletter, save_newsletter
    from app.pipeline.emailer import send_newsletter
    from app.pipeline.sanitizer import reload_blacklist
    from app.pipeline.blacklist_viability import audit_blacklist, auto_fix_collisions
    from app.pipeline.search_context import reload_profiles

    session = get_sync_session()
    stats = {}

    try:
        # Record run start
        run = Run(status="running")
        session.add(run)
        session.commit()

        # 0a. Reload configs from disk
        reload_blacklist()
        reload_profiles()

        # 0b. Blacklist viability pre-check — fix hard collisions
        log.info("pipeline.step", step="blacklist_viability")
        viability = audit_blacklist()
        hard_count = len(viability.get("hard_collisions", []))
        if hard_count > 0:
            log.warning("pipeline.blacklist_collisions", hard=hard_count)
            fix_result = auto_fix_collisions(dry_run=False)
            stats["blacklist_viability"] = {
                "hard_collisions_fixed": fix_result.get("fixed", 0),
                "soft_collisions": len(viability.get("soft_collisions", [])),
            }
            reload_blacklist()
        else:
            stats["blacklist_viability"] = {
                "hard_collisions_fixed": 0,
                "soft_collisions": len(viability.get("soft_collisions", [])),
                "entries_checked": viability.get("entries_checked", 0),
            }

        # 0c. Auto-update blacklist from AI injection research
        if settings.blacklist_auto_update:
            log.info("pipeline.step", step="blacklist_auto_update")
            try:
                from app.pipeline.blacklist_updater import auto_update_blacklist
                stats["blacklist_update"] = await auto_update_blacklist(dry_run=False)
            except Exception as exc:
                log.warning("pipeline.blacklist_update_error", error=str(exc))
                stats["blacklist_update"] = {"error": str(exc)}

        # 1. Ingest (RSS/JSON feeds + autonomous web searches via profiles)
        log.info("pipeline.step", step="ingest")
        stats["ingest"] = await ingest_sources(session)

        # 2. Normalize (includes content sanitization)
        log.info("pipeline.step", step="normalize")
        stats["normalize"] = await normalize_raw_items(session)

        # 3. Dedup
        log.info("pipeline.step", step="dedup")
        stats["dedup"] = deduplicate_articles(session)

        # 4. Extract IOCs/CVEs
        log.info("pipeline.step", step="extract")
        stats["extract"] = extract_all(session)

        # 5. Score
        log.info("pipeline.step", step="score")
        stats["score"] = score_articles(session)

        # 6. Cluster into stories
        log.info("pipeline.step", step="cluster")
        stats["cluster"] = cluster_into_stories(session)

        # 7. Generate newsletter (Devil Twins)
        log.info("pipeline.step", step="newsletter")
        newsletter_data, is_fallback = await generate_newsletter(session)
        stats["newsletter"] = {
            "is_fallback": is_fallback,
        }

        # 8. Render HTML
        log.info("pipeline.step", step="render")
        html = render_newsletter(newsletter_data, is_fallback=is_fallback)
        out_path = save_newsletter(html)
        stats["render"] = {"output": str(out_path)}

        # Also save JSON
        from pathlib import Path
        from app.settings import settings
        json_path = Path(settings.output_dir) / "latest.json"
        json_path.write_text(json.dumps(newsletter_data, indent=2, default=str))

        # 9. Send email
        log.info("pipeline.step", step="email")
        newsletter = newsletter_data.get("newsletter", newsletter_data)
        subject = newsletter.get("title", f"Cyber Newsletter — {datetime.now().strftime('%Y-%m-%d')}")
        stats["email"] = send_newsletter(html, subject=subject, dry_run=dry_run)

        # Update run record
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.stats_json = stats
        session.commit()

        log.info("pipeline.complete", status="success", dry_run=dry_run)
        return stats

    except Exception as exc:
        log.error("pipeline.error", error=str(exc))
        try:
            run.status = "error"
            run.finished_at = datetime.now(timezone.utc)
            run.error = str(exc)
            run.stats_json = stats
            session.commit()
        except Exception:
            pass
        raise

    finally:
        session.close()


@celery_app.task(name="app.pipeline.run_daily.run_daily_pipeline", bind=True, max_retries=1)
def run_daily_pipeline(self, dry_run: bool = False):
    """Celery task wrapper for the async pipeline."""
    setup_logging()
    log.info("pipeline.start", dry_run=dry_run)
    try:
        result = asyncio.run(_run_pipeline(dry_run=dry_run))
        return result
    except Exception as exc:
        log.error("pipeline.task_error", error=str(exc))
        raise


# CLI entry point
if __name__ == "__main__":
    setup_logging()
    dry = "--dry-run" in sys.argv
    print(f"Running daily pipeline (dry_run={dry})...")
    result = asyncio.run(_run_pipeline(dry_run=dry))
    print(json.dumps(result, indent=2, default=str))
