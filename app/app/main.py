from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, get_async_session
from app.settings import settings
from app.utils.logging import get_logger, setup_logging

setup_logging()
log = get_logger("api")


@asynccontextmanager
async def lifespan(application: FastAPI):
    log.info("api.startup", version="0.1.0")
    yield
    log.info("api.shutdown")


app = FastAPI(
    title="Cyber News Agent",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health(session: AsyncSession = Depends(get_async_session)):
    """Health endpoint — checks DB connectivity."""
    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar()
        db_ok = True
    except Exception:
        db_ok = False

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "db": db_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/runs")
async def list_runs(
    limit: int = 20,
    session: AsyncSession = Depends(get_async_session),
):
    """List recent pipeline runs."""
    from app.db.models import Run

    from sqlalchemy import select

    stmt = select(Run).order_by(Run.started_at.desc()).limit(limit)
    result = await session.execute(stmt)
    runs = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "stats": r.stats_json,
            "error": r.error,
        }
        for r in runs
    ]


@app.post("/api/trigger")
async def trigger_run(dry_run: bool = False):
    """Manually trigger a pipeline run via Celery."""
    from app.pipeline.run_daily import run_daily_pipeline

    task = run_daily_pipeline.delay(dry_run=dry_run)
    return {"task_id": str(task.id), "dry_run": dry_run}


@app.get("/api/stories")
async def list_stories(
    limit: int = 25,
    session: AsyncSession = Depends(get_async_session),
):
    """List top stories."""
    from app.db.models import Story

    from sqlalchemy import select

    stmt = select(Story).order_by(Story.last_seen.desc()).limit(limit)
    result = await session.execute(stmt)
    stories = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "title": s.canonical_title,
            "severity": s.severity,
            "tags": s.tags,
            "first_seen": s.first_seen.isoformat() if s.first_seen else None,
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        }
        for s in stories
    ]


@app.post("/api/reload-blacklist")
async def reload_blacklist():
    """Reload the prompt injection blacklist from disk (hot reload)."""
    from app.pipeline.sanitizer import reload_blacklist as _reload

    _reload()
    return {"status": "reloaded"}


@app.post("/api/test-sanitizer")
async def test_sanitizer(text: str):
    """Test the sanitizer against a text sample (for debugging)."""
    from app.pipeline.sanitizer import sanitize_text

    cleaned, report = sanitize_text(text, source="api_test", strict=True)
    return {
        "cleaned_text": cleaned[:500] if cleaned else "",
        "report": report,
    }
