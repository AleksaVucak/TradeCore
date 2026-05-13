"""End-to-end sentiment pipeline: fetch → score → store (Phase 17.1–17.7).

Orchestrates the full flow for a single symbol:
1. Fetch recent news headlines via NewsAPI.
2. Score each headline with VADER.
3. De-duplicate against existing DB rows using *both* headline text **and**
   article URL (Phase 17.6 tightening).
4. Persist new SentimentScore rows.

Phase 17.7 improvements:
- Pipeline is timed end-to-end; ``duration_ms`` is logged and returned.
- Every run is tagged with a ``correlation_id`` so logs from fetch → score →
  store can be correlated across services.
- Fetch status is logged at the appropriate level (WARNING for transient
  issues like rate limits, ERROR for config issues like missing key).
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.sentiment_score import SentimentScore
from app.services.sentiment.news_fetcher import (
    FetchStatus,
    fetch_news_with_status,
)
from app.services.sentiment.scorer import score_text

logger = get_logger(__name__)

_TRANSIENT_STATUSES = frozenset({
    FetchStatus.RATE_LIMITED,
    FetchStatus.HTTP_ERROR,
    FetchStatus.NETWORK_ERROR,
})


def run_sentiment_pipeline(
    db: Session,
    *,
    symbol_id: int,
    symbol: str,
    lookback_days: int = 7,
    correlation_id: str | None = None,
) -> dict:
    """Run the full sentiment pipeline for one symbol.

    Returns:
        Summary dict with counts, timing, and a ``fetch_status`` /
        ``fetch_detail`` pair so callers can surface the reason to end-users.
    """
    cid = correlation_id or uuid.uuid4().hex[:12]
    t0 = time.monotonic()

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    to_date = now.strftime("%Y-%m-%d")

    outcome = fetch_news_with_status(
        symbol, from_date=from_date, to_date=to_date
    )

    if outcome.status != FetchStatus.OK:
        duration_ms = round((time.monotonic() - t0) * 1000)
        log_fn = (
            logger.warning if outcome.status in _TRANSIENT_STATUSES
            else logger.error if outcome.status in (FetchStatus.NO_API_KEY, FetchStatus.INVALID_API_KEY)
            else logger.info
        )
        log_fn(
            "sentiment_pipeline_fetch_issue",
            correlation_id=cid,
            symbol=symbol,
            symbol_id=symbol_id,
            fetch_status=outcome.status.value,
            fetch_detail=outcome.detail,
            duration_ms=duration_ms,
        )
        return {
            "fetched": 0,
            "new": 0,
            "skipped": 0,
            "fetch_status": outcome.status.value,
            "fetch_detail": outcome.detail,
            "duration_ms": duration_ms,
            "correlation_id": cid,
        }

    articles = outcome.articles

    cutoff = now - timedelta(days=lookback_days)
    existing_rows = (
        db.query(SentimentScore.headline, SentimentScore.url)
        .filter(
            SentimentScore.symbol_id == symbol_id,
            SentimentScore.published_at >= cutoff,
        )
        .all()
    )
    existing_headlines: set[str] = {r[0] for r in existing_rows}
    existing_urls: set[str] = {r[1] for r in existing_rows if r[1]}

    new_count = 0
    skipped = 0

    for article in articles:
        url = article.url or None

        headline_dup = article.title in existing_headlines
        url_dup = bool(url and url in existing_urls)

        if headline_dup or url_dup:
            skipped += 1
            continue

        result = score_text(article.title)

        row = SentimentScore(
            symbol_id=symbol_id,
            source=article.source,
            headline=article.title,
            url=url,
            published_at=article.published_at,
            score=result.score,
            label=result.label,
        )
        db.add(row)
        existing_headlines.add(article.title)
        if url:
            existing_urls.add(url)
        new_count += 1

    db.commit()

    duration_ms = round((time.monotonic() - t0) * 1000)

    logger.info(
        "sentiment_pipeline_completed",
        correlation_id=cid,
        symbol=symbol,
        symbol_id=symbol_id,
        fetched=len(articles),
        new=new_count,
        skipped=skipped,
        duration_ms=duration_ms,
    )

    return {
        "fetched": len(articles),
        "new": new_count,
        "skipped": skipped,
        "fetch_status": FetchStatus.OK.value,
        "fetch_detail": "",
        "duration_ms": duration_ms,
        "correlation_id": cid,
    }
