"""Schemas for market data API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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


# Phase 13.1: Fetch Job schemas
class FetchRequest(BaseModel):
    """Request body for POST /market-data/fetch endpoint."""

    symbol_id: int = Field(..., description="Internal symbol id (e.g. from /symbols)")
    timeframe: str = Field(..., description="Candle interval: 1h or 4h")
    start_date: datetime = Field(..., description="Start date (UTC)")
    end_date: datetime = Field(..., description="End date (UTC)")

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        allowed = ["1h", "4h"]
        if v not in allowed:
            raise ValueError(f"timeframe must be one of {allowed}")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, v: datetime, info) -> datetime:
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class FetchJobResponse(BaseModel):
    """Response for POST /market-data/fetch — returns the created job."""

    job_id: UUID
    status: str
    symbol_id: int
    timeframe: str
    start_date: datetime
    end_date: datetime
    created_at: datetime
    message: str = "Fetch job started"

    class Config:
        from_attributes = True


class FetchJobStatusResponse(BaseModel):
    """Response for GET /market-data/fetch/{job_id} — returns job status and progress."""

    job_id: UUID
    status: str
    symbol_id: int
    timeframe: str
    start_date: datetime
    end_date: datetime

    # Progress
    total_chunks: int
    completed_chunks: int
    candles_fetched: int
    progress_pct: float

    # Error info (only present if status == "failed")
    error_message: str | None = None

    # Timestamps
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True
