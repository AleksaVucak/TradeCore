"""Celery tasks for market data ingestion."""

from datetime import datetime, timezone
from uuid import UUID

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.fetch_job import FetchJob, FetchJobStatus
from app.services.market_data.ingestion import ingest_candles
from app.services.market_data.fetch_with_progress import ingest_candles_with_progress

logger = get_logger(__name__)


@celery_app.task
def ingest_candles_task(
    symbol_id: int,
    timeframe: str,
    start_date: str,
    end_date: str,
):
    """
    Async ingest: fetch OHLCV and upsert into candles.
    start_date / end_date are ISO format (e.g. 2025-01-01T00:00:00Z).
    """
    start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    logger.info(
        "candle_ingest_started",
        symbol_id=symbol_id,
        timeframe=timeframe,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )

    db = SessionLocal()
    try:
        count = ingest_candles(db, symbol_id, timeframe, start, end)
        logger.info(
            "candle_ingest_completed",
            symbol_id=symbol_id,
            timeframe=timeframe,
            candles_upserted=count,
        )
        return {"status": "ok", "candles_upserted": count}
    except Exception as e:
        logger.exception(
            "candle_ingest_failed",
            symbol_id=symbol_id,
            timeframe=timeframe,
            error=str(e),
        )
        raise
    finally:
        db.close()


@celery_app.task
def fetch_candles_task(
    job_id: str,
    symbol_id: int,
    timeframe: str,
    start_date: str,
    end_date: str,
):
    """
    Async fetch: fetch OHLCV and upsert into candles, tracking progress in FetchJob.
    job_id is UUID string.
    start_date / end_date are ISO format (e.g. 2025-01-01T00:00:00Z).
    """
    job_uuid = UUID(job_id)
    start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    logger.info(
        "fetch_job_started",
        job_id=job_id,
        symbol_id=symbol_id,
        timeframe=timeframe,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )

    db = SessionLocal()
    try:
        job = db.get(FetchJob, job_uuid)
        if not job:
            logger.error("fetch_job_not_found", job_id=job_id)
            return {"status": "error", "message": "Job not found"}

        job.status = FetchJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        count = ingest_candles_with_progress(db, job, symbol_id, timeframe, start, end)

        job.status = FetchJobStatus.COMPLETED
        job.candles_fetched = count
        job.progress_pct = 100.0
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "fetch_job_completed",
            job_id=job_id,
            symbol_id=symbol_id,
            timeframe=timeframe,
            candles_fetched=count,
        )
        return {"status": "ok", "candles_fetched": count}
    except Exception as e:
        logger.exception(
            "fetch_job_failed",
            job_id=job_id,
            symbol_id=symbol_id,
            timeframe=timeframe,
            error=str(e),
        )
        try:
            job = db.get(FetchJob, job_uuid)
            if job:
                job.status = FetchJobStatus.FAILED
                job.error_message = str(e)[:1000]
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()
