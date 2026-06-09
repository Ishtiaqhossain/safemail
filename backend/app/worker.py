from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery = Celery(
    "safemail",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.ingestion", "app.tasks.analysis", "app.tasks.digest"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery.conf.beat_schedule = {
    "poll-all-gmail-connections": {
        "task": "app.tasks.ingestion.poll_all_connections",
        "schedule": crontab(minute=f"*/{settings.alert_poll_interval_minutes}"),
    },
    "send-weekly-digests": {
        "task": "app.tasks.digest.send_all_weekly_digests",
        "schedule": crontab(day_of_week="sun", hour=3, minute=0),
    },
    "cleanup-old-alerts": {
        "task": "app.tasks.digest.cleanup_old_data",
        "schedule": crontab(hour=2, minute=0),
    },
}
