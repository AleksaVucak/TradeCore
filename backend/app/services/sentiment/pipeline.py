"""End-to-end sentiment pipeline: fetch → score → store (Phase 17.1 + 17.5).

Orchestrates the full flow for a single symbol:
1. Fetch recent news headlines via NewsAPI.
2. Score each headline with VADER.
3. De-duplicate against existing DB rows (by headline + symbol + published_at).
4. Persist new SentimentScore rows.

Phase 17.5 — the result dict now includes a ``fetch_status`` and
``fetch_detail`` field so callers (Celery task, API) can propagate
meaningful failure reasons to the frontend.
"""

from __future__ import annotations

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


def run_sentiment_pipeline(
    db: Session,
    *,
    symbol_id: int,
    symbol: str,
    lookback_days: int = 7,
) -> dict:
    """Run the full sentiment pipeline for one symbol.

    Returns:
        Summary dict with counts *and* a ``fetch_status`` / ``fetch_detail``
        pair so callers can surface the reason to end-users.
    """
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    to_date = now.strftime("%Y-%m-%d")

    outcome = fetch_news_with_status(
        symbol, from_date=from_date, to_date=to_date
    )

    if outcome.status != FetchStatus.OK:
        logger.info(
            "sentiment_pipeline_fetch_issue",
            symbol=symbol,
            symbol_id=symbol_id,
            fetch_status=outcome.status.value,
            fetch_detail=outcome.detail,
        )
        return {
            "fetched": 0,
            "new": 0,
            "skipped": 0,
            "fetch_status": outcome.status.value,
            "fetch_detail": outcome.detail,
        }

    articles = outcome.articles

    existing_headlines = set(
        row[0]
        for row in db.query(SentimentScore.headline)
        .filter(
            SentimentScore.symbol_id == symbol_id,
            SentimentScore.published_at >= now - timedelta(days=lookback_days),
        )
        .all()
    )

    new_count = 0
    skipped = 0

    for article in articles:
        if article.title in existing_headlines:
            skipped += 1
            continue

        result = score_text(article.title)

        row = SentimentScore(
            symbol_id=symbol_id,
            source=article.source,
            headline=article.title,
            url=article.url or None,
            published_at=article.published_at,
            score=result.score,
            label=result.label,
        )
        db.add(row)
        existing_headlines.add(article.title)
        new_count += 1

    db.commit()

    logger.info(
        "sentiment_pipeline_completed",
        symbol=symbol,
        symbol_id=symbol_id,
        fetched=len(articles),
        new=new_count,
        skipped=skipped,
    )

    return {
        "fetched": len(articles),
        "new": new_count,
        "skipped": skipped,
        "fetch_status": FetchStatus.OK.value,
        "fetch_detail": "",
    }
