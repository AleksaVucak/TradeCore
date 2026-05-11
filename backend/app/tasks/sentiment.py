"""Celery tasks for the sentiment pipeline (Phase 17.1)."""

from __future__ import annotations

from typing import Any

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import SessionLocal

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def fetch_sentiment_task(
    self,
    symbol_id: int,
    symbol: str,
    lookback_days: int = 7,
) -> dict[str, Any]:
    """Fetch news + score sentiment for a single symbol.

    Intended to be called individually or from the periodic refresh task.
    """
    db = SessionLocal()
    try:
        from app.services.sentiment.pipeline import run_sentiment_pipeline

        result = run_sentiment_pipeline(
            db,
            symbol_id=symbol_id,
            symbol=symbol,
            lookback_days=lookback_days,
        )

        return {
            "status": "ok",
            "symbol_id": symbol_id,
            "symbol": symbol,
            **result,
        }
    except Exception as exc:
        logger.exception(
            "fetch_sentiment_failed",
            symbol_id=symbol_id,
            symbol=symbol,
            error=str(exc),
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "status": "failed",
                "symbol_id": symbol_id,
                "symbol": symbol,
                "error": str(exc),
            }
    finally:
        db.close()

    return {"status": "failed", "symbol_id": symbol_id, "symbol": symbol}


@celery_app.task(bind=True, max_retries=0)
def refresh_all_sentiment_task(self) -> dict[str, Any]:
    """Periodic task: refresh sentiment for all active symbols.

    Dispatches individual fetch_sentiment_task calls for each active symbol
    so they run in parallel across workers.
    """
    db = SessionLocal()
    try:
        from app.models.symbol import Symbol

        symbols = (
            db.query(Symbol)
            .filter(Symbol.is_active.is_(True))
            .all()
        )

        dispatched = 0
        for sym in symbols:
            fetch_sentiment_task.apply_async(
                kwargs={
                    "symbol_id": sym.id,
                    "symbol": sym.symbol,
                    "lookback_days": 7,
                },
            )
            dispatched += 1

        logger.info("sentiment_refresh_dispatched", count=dispatched)
        return {"status": "ok", "dispatched": dispatched}
    except Exception as exc:
        logger.exception("sentiment_refresh_failed", error=str(exc))
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()
