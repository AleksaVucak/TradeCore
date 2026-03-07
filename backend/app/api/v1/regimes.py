"""API endpoints for regime labels (9.3), performance (9.5), and models (9.6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.models.backtest_run import BacktestRun
from app.models.ml_model_metadata import MLModelMetadata
from app.models.regime_label import RegimeLabel
from app.schemas.regime import (
    ModelInfoOut,
    ModelListResponse,
    RegimeLabelOut,
    RegimeLabelResponse,
    RegimePerformanceResponse,
)
from app.services.ml.inference import get_latest_model
from app.services.ml.regime_performance import compute_regime_performance

router = APIRouter()


@router.get("", response_model=RegimeLabelResponse)
def get_regime_labels(
    symbol_id: int = Query(..., description="Symbol ID"),
    timeframe: str = Query(..., description="Candle timeframe (e.g. 1h)"),
    start: datetime | None = Query(None, description="Start time (ISO-8601)"),
    end: datetime | None = Query(None, description="End time (ISO-8601)"),
    model_id: int | None = Query(None, description="Specific model ID (optional, defaults to latest)"),
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Fetch stored regime labels for a symbol + timeframe + optional date range.

    If model_id is not provided, uses the latest model for the given
    symbol + timeframe.
    """
    if model_id is None:
        meta = get_latest_model(db, symbol_id, timeframe)
        if meta is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No trained model found for this symbol/timeframe",
            )
        model_id = meta.id

    q = (
        db.query(RegimeLabel)
        .filter(
            RegimeLabel.model_id == model_id,
            RegimeLabel.symbol_id == symbol_id,
            RegimeLabel.timeframe == timeframe,
        )
    )
    if start:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        q = q.filter(RegimeLabel.timestamp >= start)
    if end:
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        q = q.filter(RegimeLabel.timestamp <= end)

    labels = q.order_by(RegimeLabel.timestamp.asc()).all()

    return RegimeLabelResponse(
        model_id=model_id,
        symbol_id=symbol_id,
        timeframe=timeframe,
        labels=[RegimeLabelOut(timestamp=lbl.timestamp, regime=lbl.regime) for lbl in labels],
    )


@router.get("/run/{run_id}", response_model=RegimeLabelResponse)
def get_regime_labels_for_run(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Fetch stored regime labels scoped to a specific backtest run's
    symbol, timeframe, and date range.
    """
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )

    run = (
        db.query(BacktestRun)
        .filter(BacktestRun.id == run_uuid, BacktestRun.user_id == user_id)
        .first()
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )

    meta = get_latest_model(db, run.symbol_id, run.timeframe)
    if meta is None:
        return RegimeLabelResponse(
            model_id=None,
            symbol_id=run.symbol_id,
            timeframe=run.timeframe,
            labels=[],
        )

    labels = (
        db.query(RegimeLabel)
        .filter(
            RegimeLabel.model_id == meta.id,
            RegimeLabel.symbol_id == run.symbol_id,
            RegimeLabel.timeframe == run.timeframe,
            RegimeLabel.timestamp >= run.start_time,
            RegimeLabel.timestamp <= run.end_time,
        )
        .order_by(RegimeLabel.timestamp.asc())
        .all()
    )

    return RegimeLabelResponse(
        model_id=meta.id,
        symbol_id=run.symbol_id,
        timeframe=run.timeframe,
        labels=[RegimeLabelOut(timestamp=lbl.timestamp, regime=lbl.regime) for lbl in labels],
    )


@router.get("/run/{run_id}/performance", response_model=RegimePerformanceResponse)
def get_regime_performance_for_run(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Compute per-regime performance for a backtest run (Phase 9.5).

    Joins trades with regime labels and returns aggregated metrics
    (PnL, win rate, trade count) broken down by regime.
    """
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )

    run = (
        db.query(BacktestRun)
        .filter(BacktestRun.id == run_uuid, BacktestRun.user_id == user_id)
        .first()
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )

    meta = get_latest_model(db, run.symbol_id, run.timeframe)
    if meta is None:
        return RegimePerformanceResponse(
            run_id=run_id,
            total_bars=0,
            total_trades_matched=0,
            regimes=[],
        )

    result = compute_regime_performance(
        db,
        run_id=str(run.id),
        symbol_id=run.symbol_id,
        timeframe=run.timeframe,
        start_time=run.start_time,
        end_time=run.end_time,
        model_id=meta.id,
    )

    return RegimePerformanceResponse(**result)


def _model_to_info(meta: MLModelMetadata) -> ModelInfoOut:
    """Convert an MLModelMetadata row to the API response schema."""
    metrics = meta.metrics or {}
    return ModelInfoOut(
        id=meta.id,
        name=meta.name,
        symbol_id=meta.symbol_id,
        timeframe=meta.timeframe,
        training_start=meta.training_start,
        training_end=meta.training_end,
        created_at=meta.created_at,
        accuracy=metrics.get("accuracy"),
        n_train=metrics.get("n_train"),
        n_test=metrics.get("n_test"),
        tuned=metrics.get("tuned", False),
        best_params=metrics.get("best_params"),
        cv_best_score=metrics.get("cv_best_score"),
        cv_folds=metrics.get("cv_folds"),
    )


@router.get("/models", response_model=ModelListResponse)
def list_models(
    symbol_id: int | None = Query(None, description="Filter by symbol ID"),
    timeframe: str | None = Query(None, description="Filter by timeframe"),
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    List trained ML models with their accuracy, tuning info, and params (Phase 9.6).
    """
    q = db.query(MLModelMetadata)
    if symbol_id is not None:
        q = q.filter(MLModelMetadata.symbol_id == symbol_id)
    if timeframe is not None:
        q = q.filter(MLModelMetadata.timeframe == timeframe)
    models = q.order_by(MLModelMetadata.created_at.desc()).all()
    return ModelListResponse(models=[_model_to_info(m) for m in models])


@router.get("/models/{model_id}", response_model=ModelInfoOut)
def get_model(
    model_id: int,
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get details of a specific trained model (Phase 9.6).
    """
    meta = db.query(MLModelMetadata).filter(MLModelMetadata.id == model_id).first()
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )
    return _model_to_info(meta)


@router.get("/run/{run_id}/model", response_model=ModelInfoOut)
def get_model_for_run(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get the ML model info used for regime labeling of a backtest run (Phase 9.6).
    """
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )

    run = (
        db.query(BacktestRun)
        .filter(BacktestRun.id == run_uuid, BacktestRun.user_id == user_id)
        .first()
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )

    meta = get_latest_model(db, run.symbol_id, run.timeframe)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trained model found for this run's symbol/timeframe",
        )

    return _model_to_info(meta)
