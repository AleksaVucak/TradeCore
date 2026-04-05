"""Pydantic schemas for regime labels (9.3), performance (9.5), models (9.6), and training."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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


class TrainRegimeRequest(BaseModel):
    """Request body to start regime model training."""

    symbol_id: int = Field(..., description="Symbol to train on")
    timeframe: str = Field("1h", description="Candle timeframe (e.g. 1h, 4h)")
    start: str | None = Field(None, description="Training start (ISO-8601, optional)")
    end: str | None = Field(None, description="Training end (ISO-8601, optional)")
    tune: bool = Field(False, description="Enable hyperparameter tuning")


class TrainRegimeResponse(BaseModel):
    """Response after enqueuing a training job."""

    status: str
    task_id: str


class TrainStatusResponse(BaseModel):
    """Response for checking training task status (includes progress)."""

    task_id: str
    state: str
    model_id: int | None = None
    accuracy: float | None = None
    error: str | None = None
    progress_pct: int | None = None
    phase: str | None = None
