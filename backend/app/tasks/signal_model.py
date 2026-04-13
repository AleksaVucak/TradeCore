"""Celery task for ML signal model training (Phase 16.2)."""

from __future__ import annotations

from typing import Any

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import SessionLocal

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=30)
def train_signal_model_task(
    self,
    symbol_id: int,
    timeframe: str,
    feature_names: list[str],
    start_time: str | None = None,
    end_time: str | None = None,
    tune: bool = False,
    horizon: int = 5,
) -> dict[str, Any]:
    """Train an ML signal model in the background with progress reporting."""
    from datetime import datetime, timezone

    def _parse_dt(dt_str: str | None) -> datetime | None:
        if not dt_str:
            return None
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _progress(pct: int, phase: str) -> None:
        self.update_state(
            state="PROGRESS",
            meta={"progress_pct": pct, "phase": phase},
        )

    db = SessionLocal()
    try:
        from app.services.ml.signal_training import train_signal_model

        start = _parse_dt(start_time)
        end = _parse_dt(end_time)

        result = train_signal_model(
            db,
            symbol_id=symbol_id,
            timeframe=timeframe,
            feature_names=feature_names,
            start=start,
            end=end,
            horizon=horizon,
            tune=tune,
            progress_cb=_progress,
        )

        logger.info(
            "signal_model_training_completed",
            symbol_id=symbol_id,
            timeframe=timeframe,
            model_id=result["model_id"],
            accuracy=result["accuracy"],
        )

        return {
            "status": "ok",
            "model_id": result["model_id"],
            "artifact_path": result["artifact_path"],
            "accuracy": result["accuracy"],
            "n_train": result["n_train"],
            "n_test": result["n_test"],
            "label_distribution": result["label_distribution"],
            "features": result["features"],
            "horizon": result["horizon"],
            "tuned": result.get("tuned", False),
            "best_params": result.get("best_params"),
        }
    except Exception as exc:
        logger.exception(
            "signal_model_training_failed",
            symbol_id=symbol_id,
            timeframe=timeframe,
            error=str(exc),
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "status": "failed",
                "error": str(exc),
            }
    finally:
        db.close()

    return {"status": "failed"}
