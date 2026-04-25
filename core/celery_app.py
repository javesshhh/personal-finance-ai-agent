from celery import Celery
from celery.schedules import crontab

from core.config import settings

celery_app = Celery(
    "finsight",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["celery_tasks.health_score"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "weekly-health-score": {
        "task": "generate_health_score",
        "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
    },
}
