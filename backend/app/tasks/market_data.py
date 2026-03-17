"""Celery tasks for market data ingestion."""

from datetime import datetime, timezone

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.market_data.ingestion import ingest_candles

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
