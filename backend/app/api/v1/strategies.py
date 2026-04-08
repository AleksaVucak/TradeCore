from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload

from app.core.logging import get_logger
from app.dependencies import get_current_user_id, get_db
from app.models.strategy import Strategy, StrategyVersion
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
