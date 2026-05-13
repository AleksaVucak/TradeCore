"""Pydantic schemas for sentiment scores (Phase 17.1–17.7)."""

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
# Phase 17.5 + 17.7 — status endpoint
# ---------------------------------------------------------------------------

class SentimentStatusItem(BaseModel):
    """Per-symbol status summary returned by the status endpoint.

    Phase 17.7 additions:
    - ``last_refreshed_at``: the most recent ``created_at`` timestamp,
      indicating when the pipeline last stored a row for this symbol.
    - ``data_age_hours``: hours since the newest stored headline was published.
      ``None`` when no data exists yet.
    - ``is_stale``: True when the newest headline is older than the staleness
      threshold (default 48 hours) or no data exists at all.
    """

    symbol: str
    symbol_id: int
    total_scores: int
    newest_published_at: datetime | None = None
    oldest_published_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    data_age_hours: float | None = None
    is_stale: bool = False


class SentimentStatusResponse(BaseModel):
    """Overall sentiment pipeline health / status."""

    newsapi_key_set: bool
    symbols: list[SentimentStatusItem]
