"""Pydantic schemas for sentiment scores (Phase 17.1 + 17.2 + 17.5)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SentimentScoreOut(BaseModel):
    """Single sentiment score for a headline."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol_id: int
    source: str
    headline: str
    url: str | None = None
    published_at: datetime
    score: float
    label: str
    created_at: datetime


class SentimentSymbolResponse(BaseModel):
    """Paginated list of sentiment scores for a symbol (Phase 17.2)."""

    symbol: str
    symbol_id: int
    count: int
    scores: list[SentimentScoreOut]


class SentimentAggregateOut(BaseModel):
    """Aggregated sentiment statistics for a symbol (Phase 17.2)."""

    symbol: str
    symbol_id: int
    total: int
    avg_score: float
    positive_count: int
    negative_count: int
    neutral_count: int
    overall_label: str


class SentimentRefreshRequest(BaseModel):
    """Request body to trigger a manual sentiment refresh."""

    symbol_id: int = Field(..., description="Symbol to fetch news for")
    lookback_days: int = Field(7, ge=1, le=30, description="How many days back to search")


class SentimentRefreshResponse(BaseModel):
    """Response after enqueuing a sentiment refresh task."""

    status: str
    task_id: str


# ---------------------------------------------------------------------------
# Phase 17.5 — status endpoint
# ---------------------------------------------------------------------------

class SentimentStatusItem(BaseModel):
    """Per-symbol status summary returned by the status endpoint."""

    symbol: str
    symbol_id: int
    total_scores: int
    newest_published_at: datetime | None = None
    oldest_published_at: datetime | None = None


class SentimentStatusResponse(BaseModel):
    """Overall sentiment pipeline health / status."""

    newsapi_key_set: bool
    symbols: list[SentimentStatusItem]
