import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.models.backtest_run import BacktestRun, BacktestRunStatus
from app.models.strategy import Strategy, StrategyVersion
from app.models.symbol import Symbol
from app.schemas.backtest import BacktestRunDetail, BacktestRunListItem, CreateBacktestRequest
from app.tasks.backtests import run_backtest_task

router = APIRouter()


@router.get("", response_model=list[BacktestRunListItem])
def list_backtests(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = 20,
):
    runs = (
        db.query(BacktestRun)
        .filter(BacktestRun.user_id == user_id)
        .order_by(BacktestRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return runs


@router.post("", response_model=BacktestRunDetail, status_code=status.HTTP_201_CREATED)
def create_backtest(
    body: CreateBacktestRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Create a backtest run (status pending) and enqueue it for execution.
    The worker will update status to running → completed or failed.
    """
    # Ensure strategy_version belongs to user (via strategy)
    strategy_version = (
        db.query(StrategyVersion)
        .join(Strategy)
        .filter(
            StrategyVersion.id == body.strategy_version_id,
            Strategy.user_id == user_id,
        )
        .first()
    )
    if strategy_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy version not found or access denied",
        )
    # Ensure symbol exists
    if db.query(Symbol).filter(Symbol.id == body.symbol_id).first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Symbol not found",
        )
    start_dt = body.start_time
    end_dt = body.end_time
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    if start_dt >= end_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time must be before end_time",
        )

    run = BacktestRun(
        user_id=user_id,
        strategy_version_id=body.strategy_version_id,
        symbol_id=body.symbol_id,
        timeframe=body.timeframe,
        start_time=start_dt,
        end_time=end_dt,
        status=BacktestRunStatus.PENDING,
        run_options={"initial_equity": body.initial_equity},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_backtest_task.delay(
        run_id=str(run.id),
        strategy_version_id=run.strategy_version_id,
        symbol_id=run.symbol_id,
        timeframe=run.timeframe,
        start_time=run.start_time.isoformat(),
        end_time=run.end_time.isoformat(),
        initial_equity=body.initial_equity,
    )

    return run


@router.get("/{run_id}", response_model=BacktestRunDetail)
def get_backtest(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get a single backtest run by id (for polling status)."""
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
    return run
