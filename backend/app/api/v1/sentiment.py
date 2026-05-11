"""API endpoints for sentiment scores (Phase 17.2).

Exposes sentiment data stored by the Phase 17.1 pipeline so the frontend
and other consumers can query recent sentiment for any tracked symbol.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.dependencies import get_current_user_id, get_db
from app.models.sentiment_score import SentimentScore
from app.models.symbol import Symbol
from app.schemas.sentiment import (
    SentimentAggregateOut,
    SentimentRefreshRequest,
    SentimentRefreshResponse,
    SentimentScoreOut,
    SentimentSymbolResponse,
)

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/refresh",
    response_model=SentimentRefreshResponse,
    summary="Trigger a manual sentiment refresh for a symbol",
)
def trigger_sentiment_refresh(
    body: SentimentRefreshRequest,
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Enqueue a Celery task to fetch and score fresh news for the given symbol."""
    sym = db.query(Symbol).filter(Symbol.id == body.symbol_id).first()
    if not sym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol with id {body.symbol_id} not found",
        )

    from app.tasks.sentiment import fetch_sentiment_task

    result = fetch_sentiment_task.apply_async(
        kwargs={
            "symbol_id": sym.id,
            "symbol": sym.symbol,
            "lookback_days": body.lookback_days,
        },
    )

    logger.info(
        "sentiment_refresh_triggered",
        symbol=sym.symbol,
        symbol_id=sym.id,
        task_id=result.id,
    )

    return SentimentRefreshResponse(status="queued", task_id=result.id)


@router.get(
    "/{symbol}",
    response_model=SentimentSymbolResponse,
    summary="Get sentiment scores for a symbol",
)
def get_sentiment_for_symbol(
    symbol: str,
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    start: datetime | None = Query(None, description="Filter: published_at >= start (ISO-8601)"),
    end: datetime | None = Query(None, description="Filter: published_at <= end (ISO-8601)"),
    label: str | None = Query(None, description="Filter by label: positive, negative, neutral"),
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Return recent sentiment scores for a given symbol string (e.g. BTCUSD).

    - 404 if the symbol does not exist in the symbols table.
    - 200 + empty list if the symbol exists but has no sentiment data.
    """
    sym = db.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
    if not sym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found",
        )

    query = (
        db.query(SentimentScore)
        .filter(SentimentScore.symbol_id == sym.id)
    )

    if start is not None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        query = query.filter(SentimentScore.published_at >= start)

    if end is not None:
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        query = query.filter(SentimentScore.published_at <= end)

    if label is not None:
        if label.lower() not in ("positive", "negative", "neutral"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid label '{label}'. Must be positive, negative, or neutral.",
            )
        query = query.filter(SentimentScore.label == label.lower())

    scores = (
        query.order_by(SentimentScore.published_at.desc())
        .limit(limit)
        .all()
    )

    return SentimentSymbolResponse(
        symbol=sym.symbol,
        symbol_id=sym.id,
        count=len(scores),
        scores=[SentimentScoreOut.model_validate(s) for s in scores],
    )


@router.get(
    "/{symbol}/aggregate",
    response_model=SentimentAggregateOut,
    summary="Get aggregated sentiment stats for a symbol",
)
def get_sentiment_aggregate(
    symbol: str,
    start: datetime | None = Query(None, description="Filter: published_at >= start (ISO-8601)"),
    end: datetime | None = Query(None, description="Filter: published_at <= end (ISO-8601)"),
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Return aggregated sentiment statistics (avg score, label counts)."""
    sym = db.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
    if not sym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found",
        )

    base_filter = [SentimentScore.symbol_id == sym.id]

    if start is not None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        base_filter.append(SentimentScore.published_at >= start)

    if end is not None:
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        base_filter.append(SentimentScore.published_at <= end)

    stats = db.query(
        func.count(SentimentScore.id).label("total"),
        func.avg(SentimentScore.score).label("avg_score"),
    ).filter(*base_filter).first()

    total = stats.total or 0
    avg_score = round(float(stats.avg_score), 4) if stats.avg_score is not None else 0.0

    label_counts_rows = (
        db.query(SentimentScore.label, func.count(SentimentScore.id))
        .filter(*base_filter)
        .group_by(SentimentScore.label)
        .all()
    )
    label_counts = {row[0]: row[1] for row in label_counts_rows}

    if total > 0:
        overall_label = max(label_counts, key=label_counts.get)
    else:
        overall_label = "neutral"

    return SentimentAggregateOut(
        symbol=sym.symbol,
        symbol_id=sym.id,
        total=total,
        avg_score=avg_score,
        positive_count=label_counts.get("positive", 0),
        negative_count=label_counts.get("negative", 0),
        neutral_count=label_counts.get("neutral", 0),
        overall_label=overall_label,
    )
