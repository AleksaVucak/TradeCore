"""Schemas for market data API."""

from datetime import datetime

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    symbol_id: int = Field(..., description="Internal symbol id (e.g. from /symbols)")
    timeframe: str = Field(..., description="Candle interval: 1h or 4h")
    start_date: datetime
    end_date: datetime


class IngestResponse(BaseModel):
    message: str = "Ingestion started"
    task_id: str | None = None


class CandleResponse(BaseModel):
    id: int
    symbol_id: int
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    class Config:
        from_attributes = True
