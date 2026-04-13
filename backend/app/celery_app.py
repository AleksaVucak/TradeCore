from celery import Celery
from celery.signals import worker_process_init

from app.config import settings

celery_app = Celery(
    "tradecore",
    broker=settings.celery_broker_url,
    backend=settings.redis_url,
    include=["app.tasks", "app.tasks.market_data", "app.tasks.regimes", "app.tasks.signal_model"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@worker_process_init.connect
def init_worker_logging(**kwargs):
    """Initialize structured logging when Celery worker starts."""
    from app.core.logging import configure_logging, get_logger
    
    configure_logging()
    logger = get_logger("celery.worker")
    logger.info("celery_worker_initialized")
