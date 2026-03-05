from celery import Celery
from celery.schedules import crontab

from app.settings import settings

app = Celery(
    "cyberagent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.tz,
    enable_utc=True,
    task_track_started=True,
    task_default_queue="default",
    task_routes={
        "app.pipeline.run_daily.run_daily_pipeline": {"queue": "pipeline"},
    },
)

# Parse DAILY_RUN_TIME "HH:MM"
_hour, _minute = settings.daily_run_time.split(":")

app.conf.beat_schedule = {
    "daily-newsletter": {
        "task": "app.pipeline.run_daily.run_daily_pipeline",
        "schedule": crontab(hour=int(_hour), minute=int(_minute)),
        "kwargs": {"dry_run": False},
    },
}
