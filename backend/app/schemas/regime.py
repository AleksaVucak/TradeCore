"""Pydantic schemas for regime labels (Phase 9.3)."""

from datetime import datetime

from pydantic import BaseModel


class RegimeLabelOut(BaseModel):
    """Single regime label for a bar."""

    timestamp: datetime
    regime: str

    class Config:
        from_attributes = True


class RegimeLabelResponse(BaseModel):
    """Response for bulk regime label queries."""

    model_id: int | None = None
    symbol_id: int
    timeframe: str
    labels: list[RegimeLabelOut]
