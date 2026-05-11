"""End-to-end sentiment pipeline: fetch → score → store (Phase 17.1).

Orchestrates the full flow for a single symbol:
1. Fetch recent news headlines via NewsAPI.
2. Score each headline with VADER.
3. De-duplicate against existing DB rows (by headline + symbol + published_at).
4. Persist new SentimentScore rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.sentiment_score import SentimentScore
from app.services.sentiment.news_fetcher import NewsArticle, fetch_news
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

    Args:
        db: SQLAlchemy session.
        symbol_id: Internal symbol PK.
        symbol: Trading pair string (e.g. "BTCUSDT") used for the news query.
        lookback_days: How far back to search for articles.

    Returns:
        Summary dict with counts of fetched, new, and skipped articles.
    """
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    to_date = now.strftime("%Y-%m-%d")

    articles: list[NewsArticle] = fetch_news(
        symbol, from_date=from_date, to_date=to_date
    )

    if not articles:
        logger.info(
            "sentiment_pipeline_no_articles",
            symbol=symbol,
            symbol_id=symbol_id,
        )
        return {"fetched": 0, "new": 0, "skipped": 0}

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

    return {"fetched": len(articles), "new": new_count, "skipped": skipped}
