"""Celery task for auto-labeling regimes after a backtest completes."""

from __future__ import annotations

from typing import Any

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.ml.inference import get_latest_model, label_candles

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def label_regimes_for_run_task(
    self,
    run_id: str,
    symbol_id: int,
    timeframe: str,
    start_time: str,
    end_time: str,
) -> dict[str, Any]:
    """Label regime data for the date range of a completed backtest run.

    Skipped silently when no trained model exists for the symbol+timeframe
    (regimes are opt-in; training must happen first via CLI or scheduled job).
    """
    from datetime import datetime, timezone

    def _parse_dt(dt_str: str) -> datetime:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    db = SessionLocal()
    try:
        meta = get_latest_model(db, symbol_id, timeframe)
        if meta is None:
            logger.info(
                "regime_labeling_skipped_no_model",
                run_id=run_id,
                symbol_id=symbol_id,
                timeframe=timeframe,
            )
            return {
                "status": "skipped",
                "reason": "no_trained_model",
                "run_id": run_id,
            }

        start_dt = _parse_dt(start_time)
        end_dt = _parse_dt(end_time)

        result = label_candles(
            db,
            symbol_id=symbol_id,
            timeframe=timeframe,
            start=start_dt,
            end=end_dt,
            backtest_run_id=run_id,
        )

        logger.info(
            "regime_labeling_completed",
            run_id=run_id,
            symbol_id=symbol_id,
            timeframe=timeframe,
            labeled_bars=result["labeled_bars"],
        )

        return {
            "status": "ok",
            "run_id": run_id,
            **result,
        }
    except Exception as exc:
        logger.exception(
            "regime_labeling_failed",
            run_id=run_id,
            symbol_id=symbol_id,
            timeframe=timeframe,
            error=str(exc),
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "status": "failed",
                "run_id": run_id,
                "error": str(exc),
            }
    finally:
        db.close()

    return {"status": "failed", "run_id": run_id}
