"""Pydantic schemas for regime labels (9.3), performance (9.5), and models (9.6)."""

from datetime import datetime
from typing import Any

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


class ModelInfoOut(BaseModel):
    """Summary of a trained ML model (Phase 9.6)."""

    id: int
    name: str
    symbol_id: int | None = None
    timeframe: str | None = None
    training_start: datetime | None = None
    training_end: datetime | None = None
    created_at: datetime
    accuracy: float | None = None
    n_train: int | None = None
    n_test: int | None = None
    tuned: bool = False
    best_params: dict[str, Any] | None = None
    cv_best_score: float | None = None
    cv_folds: int | None = None

    class Config:
        from_attributes = True


class ModelListResponse(BaseModel):
    """Response listing trained models (Phase 9.6)."""

    models: list[ModelInfoOut]


class EnsureRegimesResponse(BaseModel):
    """Response from the ensure-regimes endpoint."""

    status: str
    labeled_bars: int = 0
    model_id: int | None = None
