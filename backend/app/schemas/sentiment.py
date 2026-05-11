"""Pydantic schemas for sentiment scores (Phase 17.1)."""

from datetime import datetime

from pydantic import BaseModel, Field


class SentimentScoreOut(BaseModel):
    """Single sentiment score for a headline."""

    id: int
    symbol_id: int
    source: str
    headline: str
    url: str | None = None
    published_at: datetime
    score: float
    label: str
    created_at: datetime

    class Config:
        from_attributes = True


class SentimentRefreshRequest(BaseModel):
    """Request body to trigger a manual sentiment refresh."""

    symbol_id: int = Field(..., description="Symbol to fetch news for")
    lookback_days: int = Field(7, ge=1, le=30, description="How many days back to search")


class SentimentRefreshResponse(BaseModel):
    """Response after enqueuing a sentiment refresh task."""

    status: str
    task_id: str
