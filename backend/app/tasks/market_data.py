"""Celery tasks for market data ingestion."""

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.market_data.ingestion import ingest_candles

logger = logging.getLogger(__name__)


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

    db = SessionLocal()
    try:
        count = ingest_candles(db, symbol_id, timeframe, start, end)
        logger.info("Ingest completed: symbol_id=%s timeframe=%s candles=%s", symbol_id, timeframe, count)
        return {"status": "ok", "candles_upserted": count}
    except Exception as e:
        logger.exception("Ingest failed: symbol_id=%s timeframe=%s error=%s", symbol_id, timeframe, e)
        raise
    finally:
        db.close()
