"""API endpoints for regime labels (9.3), performance (9.5), and models (9.6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.dependencies import get_current_user_id, get_db
from app.models.backtest_run import BacktestRun
from app.models.ml_model_metadata import MLModelMetadata
from app.models.regime_label import RegimeLabel
from app.schemas.regime import (
    EnsureRegimesResponse,
    ModelInfoOut,
    ModelListResponse,
    RegimeLabelOut,
    RegimeLabelResponse,
    RegimePerformanceResponse,
    TrainRegimeRequest,
    TrainRegimeResponse,
    TrainStatusResponse,
)
from app.services.ml.inference import get_latest_model, label_candles
from app.services.ml.regime_performance import compute_regime_performance

logger = get_logger(__name__)

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


@router.post("/run/{run_id}/ensure", response_model=EnsureRegimesResponse)
def ensure_regimes_for_run(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Ensure regime labels exist for a backtest run's date range.

    If labels already exist for the latest model, returns immediately.
    If a trained model exists but labels are missing, runs inference and
    persists them. Returns 200 with status="no_model" when no trained
    model is available (training is a separate, explicit step).
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
        return EnsureRegimesResponse(status="no_model")

    existing_count = (
        db.query(RegimeLabel)
        .filter(
            RegimeLabel.model_id == meta.id,
            RegimeLabel.symbol_id == run.symbol_id,
            RegimeLabel.timeframe == run.timeframe,
            RegimeLabel.timestamp >= run.start_time,
            RegimeLabel.timestamp <= run.end_time,
        )
        .count()
    )
    if existing_count > 0:
        return EnsureRegimesResponse(
            status="already_labeled",
            labeled_bars=existing_count,
            model_id=meta.id,
        )

    try:
        result = label_candles(
            db,
            symbol_id=run.symbol_id,
            timeframe=run.timeframe,
            start=run.start_time,
            end=run.end_time,
            backtest_run_id=run_id,
        )
    except ValueError as exc:
        logger.warning(
            "ensure_regimes_insufficient_data",
            run_id=run_id,
            error=str(exc),
        )
        return EnsureRegimesResponse(status="insufficient_data", model_id=meta.id)

    logger.info(
        "ensure_regimes_labeled",
        run_id=run_id,
        labeled_bars=result["labeled_bars"],
        model_id=meta.id,
    )
    return EnsureRegimesResponse(
        status="labeled",
        labeled_bars=result["labeled_bars"],
        model_id=meta.id,
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
        model_type=metrics.get("model_type"),
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


@router.post("/train", response_model=TrainRegimeResponse, status_code=status.HTTP_202_ACCEPTED)
def start_regime_training(
    body: TrainRegimeRequest,
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Start training a regime classification model in the background.

    Enqueues a Celery task and returns immediately with a task ID.
    The trained model will appear in GET /regimes/models once complete.
    """
    from app.models.symbol import Symbol

    symbol = db.query(Symbol).filter(Symbol.id == body.symbol_id).first()
    if symbol is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol with id {body.symbol_id} not found",
        )

    from app.tasks.regimes import train_regime_model_task

    result = train_regime_model_task.apply_async(
        kwargs={
            "symbol_id": body.symbol_id,
            "timeframe": body.timeframe,
            "start_time": body.start,
            "end_time": body.end,
            "tune": body.tune,
        },
    )

    logger.info(
        "regime_training_enqueued",
        task_id=result.id,
        symbol_id=body.symbol_id,
        timeframe=body.timeframe,
        tune=body.tune,
    )

    return TrainRegimeResponse(status="queued", task_id=result.id)


@router.get("/train/status/{task_id}", response_model=TrainStatusResponse)
def get_training_status(
    task_id: str,
    _user_id: int = Depends(get_current_user_id),
):
    """Check the status of a regime model training task (includes progress)."""
    from celery.result import AsyncResult

    from app.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)
    state = result.state

    model_id: int | None = None
    accuracy: float | None = None
    error: str | None = None
    progress_pct: int | None = None
    phase: str | None = None

    if state == "PROGRESS" and isinstance(result.info, dict):
        progress_pct = result.info.get("progress_pct")
        phase = result.info.get("phase")
    elif state == "SUCCESS" and isinstance(result.result, dict):
        progress_pct = 100
        phase = "Complete"
        model_id = result.result.get("model_id")
        accuracy = result.result.get("accuracy")
        if result.result.get("status") == "failed":
            state = "FAILURE"
            error = result.result.get("error", "Training failed")
            progress_pct = None
            phase = None
    elif state == "FAILURE":
        error = str(result.result) if result.result else "Training failed"
    elif state in ("PENDING", "STARTED"):
        progress_pct = 0
        phase = "Queued"

    return TrainStatusResponse(
        task_id=task_id,
        state=state,
        model_id=model_id,
        accuracy=accuracy,
        error=error,
        progress_pct=progress_pct,
        phase=phase,
    )


@router.get("/models", response_model=ModelListResponse)
def list_models(
    symbol_id: int | None = Query(None, description="Filter by symbol ID"),
    timeframe: str | None = Query(None, description="Filter by timeframe"),
    model_type: str | None = Query(None, description="Filter by model type (e.g. 'signal', 'regime')"),
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
    rows = q.order_by(MLModelMetadata.created_at.desc()).all()
    if model_type is not None:
        rows = [m for m in rows if (m.metrics or {}).get("model_type") == model_type]
    return ModelListResponse(models=[_model_to_info(m) for m in rows])


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
