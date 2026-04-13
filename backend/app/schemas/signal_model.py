"""Pydantic schemas for ML signal model training (Phase 16.2)."""

from pydantic import BaseModel, Field


class TrainSignalRequest(BaseModel):
    """Request body to start signal model training."""

    symbol_id: int = Field(..., description="Symbol to train on")
    timeframe: str = Field("1h", description="Candle timeframe (e.g. 1h, 4h)")
    features: list[str] = Field(
        ..., min_length=1, description="Feature names to train with"
    )
    start: str | None = Field(None, description="Training start (ISO-8601, optional)")
    end: str | None = Field(None, description="Training end (ISO-8601, optional)")
    tune: bool = Field(False, description="Enable hyperparameter tuning")
    horizon: int = Field(5, ge=1, le=50, description="Forward-looking bars for label generation")


class TrainSignalResponse(BaseModel):
    """Response after enqueuing a signal training job."""

    status: str
    task_id: str


class TrainSignalStatusResponse(BaseModel):
    """Response for checking signal training task status (includes progress)."""

    task_id: str
    state: str
    model_id: int | None = None
    accuracy: float | None = None
    error: str | None = None
    progress_pct: int | None = None
    phase: str | None = None
