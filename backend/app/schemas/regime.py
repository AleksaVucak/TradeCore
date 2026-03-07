"""Pydantic schemas for regime labels (Phase 9.3) and performance (Phase 9.5)."""

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


class RegimePerformanceItem(BaseModel):
    """Performance metrics for a single regime (Phase 9.5)."""

    regime: str
    label: str
    bars: int
    bars_pct: float
    num_trades: int
    total_pnl: float
    avg_pnl: float | None = None
    win_rate: float | None = None
    wins: int = 0
    losses: int = 0


class RegimePerformanceResponse(BaseModel):
    """Per-regime performance breakdown for a backtest run (Phase 9.5)."""

    run_id: str
    total_bars: int
    total_trades_matched: int
    regimes: list[RegimePerformanceItem]
