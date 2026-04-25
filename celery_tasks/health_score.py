from core.celery_app import celery_app


@celery_app.task(name="generate_health_score")
def generate_health_score_task() -> dict:
    """Celery task: generate and persist this week's health score.

    Implemented in Phase 06. Placeholder returns a stub until then.
    """
    return {"status": "not_implemented_until_phase_06"}
