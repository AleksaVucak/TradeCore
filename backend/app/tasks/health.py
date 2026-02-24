from app.celery_app import celery_app


@celery_app.task
def ping():
    """No-op task to verify worker is running."""
    return "pong"
