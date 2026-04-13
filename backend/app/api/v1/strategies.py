from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload

from app.core.logging import get_logger
from app.dependencies import get_current_user_id, get_db
from app.models.strategy import Strategy, StrategyVersion
from app.schemas.signal_model import (
    TrainSignalRequest,
    TrainSignalResponse,
    TrainSignalStatusResponse,
)
from app.schemas.strategy import (
    CreateStrategyRequest,
    CreateStrategyVersionRequest,
    StrategyDetail,
    StrategyListItem,
    UpdateStrategyRequest,
)
from app.schemas.strategy_config import ML_FEATURE_CATALOG, validate_strategy_config

logger = get_logger(__name__)

router = APIRouter()


def _get_strategy_for_user_or_404(
    strategy_id: int,
    user_id: int,
    db: Session,
) -> Strategy:
    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.versions))
        .filter(Strategy.id == strategy_id, Strategy.user_id == user_id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


def _validate_strategy_config_or_422(strategy_type: str, config: dict):
    try:
        return validate_strategy_config(strategy_type, config)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get("/ml-features", response_model=list[str])
def list_ml_features() -> list[str]:
    """Return the canonical list of ML features the platform supports."""
    return ML_FEATURE_CATALOG


@router.get("", response_model=list[StrategyListItem])
def list_strategies(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    strategies = (
        db.query(Strategy)
        .filter(Strategy.user_id == user_id)
        .order_by(Strategy.created_at.desc())
        .limit(limit)
        .all()
    )
    return strategies


@router.post(
    "",
    response_model=StrategyDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_strategy(
    body: CreateStrategyRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Create a new strategy for the current user with an initial active version.

    The config is validated according to strategy_type before being stored.
    """
    validated = _validate_strategy_config_or_422(body.strategy_type, body.config)

    strategy = Strategy(
        user_id=user_id,
        name=body.name,
        description=body.description,
        strategy_type=body.strategy_type,
    )
    db.add(strategy)
    db.flush()  # populate strategy.id

    config_dict = (
        validated.to_config_dict()
        if hasattr(validated, "to_config_dict")
        else validated.model_dump()
    )

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=1,
        config=config_dict,
        is_active=True,
    )
    db.add(version)
    db.commit()

    logger.info(
        "strategy_created",
        strategy_id=strategy.id,
        user_id=user_id,
        name=body.name,
        strategy_type=body.strategy_type,
    )

    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.versions))
        .filter(Strategy.id == strategy.id)
        .one()
    )
    return strategy


@router.get(
    "/{strategy_id}",
    response_model=StrategyDetail,
)
def get_strategy(
    strategy_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get a single strategy owned by the current user, including all versions.
    """
    strategy = _get_strategy_for_user_or_404(strategy_id, user_id, db)
    return strategy


@router.patch(
    "/{strategy_id}",
    response_model=StrategyDetail,
)
def update_strategy(
    strategy_id: int,
    body: UpdateStrategyRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Update strategy metadata (name / description).
    """
    strategy = _get_strategy_for_user_or_404(strategy_id, user_id, db)

    if body.name is not None:
        strategy.name = body.name
    if body.description is not None:
        strategy.description = body.description

    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    # ensure versions are loaded
    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.versions))
        .filter(Strategy.id == strategy.id)
        .one()
    )
    return strategy


@router.post(
    "/{strategy_id}/versions",
    response_model=StrategyDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_strategy_version(
    strategy_id: int,
    body: CreateStrategyVersionRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Create a new version for a strategy and mark it as active.
    """
    strategy = _get_strategy_for_user_or_404(strategy_id, user_id, db)

    validated = _validate_strategy_config_or_422(strategy.strategy_type, body.config)
    config_dict = (
        validated.to_config_dict()
        if hasattr(validated, "to_config_dict")
        else validated.model_dump()
    )

    current_max_version = max((v.version_number for v in strategy.versions), default=0)

    for v in strategy.versions:
        if v.is_active:
            v.is_active = False

    new_version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=current_max_version + 1,
        config=config_dict,
        is_active=True,
    )
    db.add(new_version)
    db.commit()

    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.versions))
        .filter(Strategy.id == strategy.id)
        .one()
    )
    return strategy


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_strategy(
    strategy_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Delete a strategy owned by the current user (and all its versions).
    """
    strategy = _get_strategy_for_user_or_404(strategy_id, user_id, db)
    db.delete(strategy)
    db.commit()
    logger.info("strategy_deleted", strategy_id=strategy_id, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# ML Signal model training endpoints (Phase 16.2)
# ---------------------------------------------------------------------------


@router.post(
    "/ml-signal/train",
    response_model=TrainSignalResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_signal_training(
    body: TrainSignalRequest,
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Start training an ML signal model in the background.

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

    unknown = set(body.features) - set(ML_FEATURE_CATALOG)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown features: {sorted(unknown)}. Allowed: {ML_FEATURE_CATALOG}",
        )

    from app.tasks.signal_model import train_signal_model_task

    result = train_signal_model_task.apply_async(
        kwargs={
            "symbol_id": body.symbol_id,
            "timeframe": body.timeframe,
            "feature_names": body.features,
            "start_time": body.start,
            "end_time": body.end,
            "tune": body.tune,
            "horizon": body.horizon,
        },
    )

    logger.info(
        "signal_training_enqueued",
        task_id=result.id,
        symbol_id=body.symbol_id,
        timeframe=body.timeframe,
        features=body.features,
        tune=body.tune,
        horizon=body.horizon,
    )

    return TrainSignalResponse(status="queued", task_id=result.id)


@router.get("/ml-signal/train/status/{task_id}", response_model=TrainSignalStatusResponse)
def get_signal_training_status(
    task_id: str,
    _user_id: int = Depends(get_current_user_id),
):
    """Check the status of an ML signal model training task."""
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

    return TrainSignalStatusResponse(
        task_id=task_id,
        state=state,
        model_id=model_id,
        accuracy=accuracy,
        error=error,
        progress_pct=progress_pct,
        phase=phase,
    )
