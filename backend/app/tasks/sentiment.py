"""Celery tasks for the sentiment pipeline (Phase 17.1–17.7).

Phase 17.7 improvements:
- Smart retry: only retries on *transient* failures (rate limit, network,
  HTTP 5xx).  Config errors (missing/invalid API key) and empty results
  are **not** retried — those need human intervention.
- Exponential backoff: retry delays double each attempt (60s → 120s → …).
- Correlation ID: generated per task execution and threaded through the
  pipeline so all logs for one refresh are correlated.
- Duration and retry count are included in the return dict.
- ``refresh_all_sentiment_task`` adds inter-symbol spacing to avoid
  hammering NewsAPI when many symbols are active.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.sentiment.news_fetcher import FetchStatus

logger = get_logger(__name__)

_RETRYABLE_STATUSES = frozenset({
    FetchStatus.RATE_LIMITED.value,
    FetchStatus.HTTP_ERROR.value,
    FetchStatus.NETWORK_ERROR.value,
})


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(),
    acks_late=True,
)
def fetch_sentiment_task(
    self,
    symbol_id: int,
    symbol: str,
    lookback_days: int = 7,
) -> dict[str, Any]:
    """Fetch news + score sentiment for a single symbol.

    Returns a result dict that includes ``fetch_status``, timing, and
    the ``correlation_id`` for log correlation.
    """
    cid = uuid.uuid4().hex[:12]
    attempt = self.request.retries + 1

    logger.info(
        "sentiment_task_started",
        correlation_id=cid,
        symbol=symbol,
        symbol_id=symbol_id,
        attempt=attempt,
        max_retries=self.max_retries,
    )

    db = SessionLocal()
    try:
        from app.services.sentiment.pipeline import run_sentiment_pipeline

        result = run_sentiment_pipeline(
            db,
            symbol_id=symbol_id,
            symbol=symbol,
            lookback_days=lookback_days,
            correlation_id=cid,
        )

        fetch_status = result.get("fetch_status", "")

        if fetch_status in _RETRYABLE_STATUSES and attempt <= self.max_retries:
            backoff = 60 * (2 ** (attempt - 1))
            logger.warning(
                "sentiment_task_retrying",
                correlation_id=cid,
                symbol=symbol,
                symbol_id=symbol_id,
                fetch_status=fetch_status,
                attempt=attempt,
                backoff_seconds=backoff,
            )
            raise self.retry(
                countdown=backoff,
                exc=RuntimeError(f"Transient fetch failure: {fetch_status}"),
            )

        logger.info(
            "sentiment_task_completed",
            correlation_id=cid,
            symbol=symbol,
            symbol_id=symbol_id,
            fetch_status=fetch_status,
            fetched=result.get("fetched", 0),
            new=result.get("new", 0),
            skipped=result.get("skipped", 0),
            duration_ms=result.get("duration_ms"),
            attempt=attempt,
        )

        return {
            "status": "ok" if fetch_status == "ok" else "completed_with_issue",
            "symbol_id": symbol_id,
            "symbol": symbol,
            "attempt": attempt,
            "correlation_id": cid,
            **result,
        }

    except self.MaxRetriesExceededError:
        logger.error(
            "sentiment_task_max_retries_exceeded",
            correlation_id=cid,
            symbol=symbol,
            symbol_id=symbol_id,
            attempt=attempt,
        )
        return {
            "status": "failed",
            "symbol_id": symbol_id,
            "symbol": symbol,
            "error": "Max retries exceeded for transient failure",
            "fetch_status": "error",
            "fetch_detail": "Pipeline failed after all retry attempts.",
            "attempt": attempt,
            "correlation_id": cid,
        }
    except Exception as exc:
        if isinstance(exc, self.MaxRetriesExceededError):
            raise

        logger.exception(
            "sentiment_task_unexpected_error",
            correlation_id=cid,
            symbol_id=symbol_id,
            symbol=symbol,
            error=str(exc),
            attempt=attempt,
        )
        return {
            "status": "failed",
            "symbol_id": symbol_id,
            "symbol": symbol,
            "error": str(exc),
            "fetch_status": "error",
            "fetch_detail": str(exc),
            "attempt": attempt,
            "correlation_id": cid,
        }
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=0)
def refresh_all_sentiment_task(self) -> dict[str, Any]:
    """Periodic task: refresh sentiment for all active symbols.

    Dispatches individual fetch_sentiment_task calls for each active symbol
    with staggered countdowns (Phase 17.7) so NewsAPI isn't overwhelmed
    when many symbols are active.
    """
    cid = uuid.uuid4().hex[:12]

    db = SessionLocal()
    try:
        from app.models.symbol import Symbol

        symbols = (
            db.query(Symbol)
            .filter(Symbol.is_active.is_(True))
            .all()
        )

        dispatched = 0
        for i, sym in enumerate(symbols):
            fetch_sentiment_task.apply_async(
                kwargs={
                    "symbol_id": sym.id,
                    "symbol": sym.symbol,
                    "lookback_days": 7,
                },
                countdown=i * 10,
            )
            dispatched += 1

        logger.info(
            "sentiment_refresh_dispatched",
            correlation_id=cid,
            count=dispatched,
            spacing_seconds=10,
        )
        return {
            "status": "ok",
            "dispatched": dispatched,
            "correlation_id": cid,
        }
    except Exception as exc:
        logger.exception(
            "sentiment_refresh_failed",
            correlation_id=cid,
            error=str(exc),
        )
        return {
            "status": "failed",
            "error": str(exc),
            "correlation_id": cid,
        }
    finally:
        db.close()
