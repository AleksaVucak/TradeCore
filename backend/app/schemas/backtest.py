from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BacktestRunListItem(BaseModel):
    id: UUID
    symbol_id: int
    timeframe: str
    status: str
    start_time: datetime
    end_time: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class CreateBacktestRequest(BaseModel):
    strategy_version_id: int = Field(..., description="Strategy version to run")
    symbol_id: int = Field(..., description="Symbol (e.g. BTC)")
    timeframe: str = Field(..., description="Candle interval: 1h or 4h")
    start_time: datetime = Field(..., description="Backtest start (UTC)")
    end_time: datetime = Field(..., description="Backtest end (UTC)")
    initial_equity: float = Field(10_000.0, ge=0.01, description="Starting equity")


class BacktestRunDetail(BaseModel):
    id: UUID
    symbol_id: int
    timeframe: str
    status: str
    start_time: datetime
    end_time: datetime
    created_at: datetime
    error_message: str | None = None

    class Config:
        from_attributes = True
