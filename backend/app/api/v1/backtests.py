import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.logging import get_logger
from app.dependencies import get_current_user_id, get_db
from app.models.backtest_run import BacktestRun, BacktestRunStatus
from app.models.strategy import Strategy, StrategyVersion
from app.models.symbol import Symbol
from app.schemas.backtest import (
    BacktestRunDetail,
    BacktestRunListItem,
    CreateBacktestRequest,
    EquityPointOut,
    RiskMetricsResponse,
    TradeOut,
)
from app.services.backtest.risk_metrics import compute_risk_metrics
from app.tasks.backtests import run_backtest_task

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=list[BacktestRunListItem])
def list_backtests(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = 20,
):
    """List backtest runs with symbol, strategy, return, drawdown for run history (Phase 8.1)."""
    runs = (
        db.query(BacktestRun)
        .options(
            joinedload(BacktestRun.symbol),
            joinedload(BacktestRun.strategy_version).joinedload(StrategyVersion.strategy),
            joinedload(BacktestRun.metrics),
        )
        .filter(BacktestRun.user_id == user_id)
        .order_by(BacktestRun.created_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for r in runs:
        metrics = r.metrics.metrics if r.metrics else {}
        out.append(
            BacktestRunListItem(
                id=r.id,
                symbol_id=r.symbol_id,
                symbol_name=r.symbol.symbol if r.symbol else None,
                strategy_name=r.strategy_version.strategy.name if r.strategy_version and r.strategy_version.strategy else None,
                timeframe=r.timeframe,
                status=r.status,
                start_time=r.start_time,
                end_time=r.end_time,
                created_at=r.created_at,
                error_message=r.error_message,
                total_return_pct=metrics.get("total_return_pct"),
                max_drawdown_pct=metrics.get("max_drawdown_pct"),
            )
        )
    return out


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

    logger.info(
        "backtest_created",
        run_id=str(run.id),
        user_id=user_id,
        strategy_version_id=body.strategy_version_id,
        symbol_id=body.symbol_id,
        timeframe=body.timeframe,
    )

    return BacktestRunDetail(
        id=run.id,
        symbol_id=run.symbol_id,
        timeframe=run.timeframe,
        status=run.status,
        start_time=run.start_time,
        end_time=run.end_time,
        created_at=run.created_at,
        error_message=run.error_message,
        trades=[],
        equity_curve=[],
        metrics=None,
    )


def _get_run_for_user(db: Session, run_id: str, user_id: int) -> BacktestRun | None:
    """Load run by id if it belongs to user; return None if not found or invalid."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        return None
    return (
        db.query(BacktestRun)
        .filter(BacktestRun.id == run_uuid, BacktestRun.user_id == user_id)
        .first()
    )


@router.get("/{run_id}/trades", response_model=list[TradeOut])
def get_backtest_trades(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get trades for a backtest run (Phase 7.2)."""
    run = _get_run_for_user(db, run_id, user_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )
    run = db.query(BacktestRun).options(joinedload(BacktestRun.trades)).get(run.id)
    return [TradeOut.model_validate(t) for t in run.trades]


@router.get("/{run_id}/equity", response_model=list[EquityPointOut])
def get_backtest_equity(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get equity curve for a backtest run (Phase 7.2)."""
    run = _get_run_for_user(db, run_id, user_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )
    run = (
        db.query(BacktestRun)
        .options(
            joinedload(BacktestRun.equity_snapshots),
            joinedload(BacktestRun.metrics),
        )
        .get(run.id)
    )
    equity_snapshots = sorted(run.equity_snapshots, key=lambda s: s.timestamp)
    if equity_snapshots:
        return [
            EquityPointOut(timestamp=s.timestamp, equity_value=s.equity_value)
            for s in equity_snapshots
        ]
    # Completed run with no snapshots: return minimal flat curve
    if run.status == "completed":
        initial_value = 10_000.0
        if run.metrics and isinstance(run.metrics.metrics, dict):
            initial_value = float(run.metrics.metrics.get("final_equity", initial_value))
        return [
            EquityPointOut(timestamp=run.start_time, equity_value=initial_value),
            EquityPointOut(timestamp=run.end_time, equity_value=initial_value),
        ]
    return []


@router.get("/{run_id}/metrics")
def get_backtest_metrics(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get metrics snapshot for a backtest run (Phase 7.2). Returns 404 if not yet available."""
    run = _get_run_for_user(db, run_id, user_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )
    run = (
        db.query(BacktestRun)
        .options(joinedload(BacktestRun.metrics))
        .get(run.id)
    )
    if run.metrics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metrics not available for this run (run may still be pending or failed)",
        )
    return run.metrics.metrics


@router.get("/{run_id}/risk-metrics", response_model=RiskMetricsResponse)
def get_backtest_risk_metrics(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get advanced risk metrics for a completed backtest run (Phase 12.2).

    Computes Sortino ratio, Calmar ratio, VaR/CVaR, and detailed trade statistics
    from the equity curve and trades data.

    Returns 404 if the run is not found or not yet completed.
    """
    run = _get_run_for_user(db, run_id, user_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )

    # Load full run data with equity snapshots and trades
    run = (
        db.query(BacktestRun)
        .options(
            joinedload(BacktestRun.equity_snapshots),
            joinedload(BacktestRun.trades),
            joinedload(BacktestRun.metrics),
        )
        .get(run.id)
    )

    if run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Risk metrics only available for completed runs (current status: {run.status})",
        )

    # Extract equity curve data
    equity_snapshots = sorted(run.equity_snapshots, key=lambda s: s.timestamp)
    equity_values = [s.equity_value for s in equity_snapshots]
    equity_timestamps = [s.timestamp for s in equity_snapshots]

    # Get initial equity from run options or default
    initial_equity = 10_000.0
    if run.run_options and isinstance(run.run_options, dict):
        initial_equity = float(run.run_options.get("initial_equity", 10_000.0))

    # If no equity snapshots but run is completed, use metrics data
    if not equity_values and run.metrics and isinstance(run.metrics.metrics, dict):
        final_eq = float(run.metrics.metrics.get("final_equity", initial_equity))
        equity_values = [initial_equity, final_eq]
        equity_timestamps = [run.start_time, run.end_time]

    # Extract trade P&Ls (only closed trades with realized P&L)
    trade_pnls = [
        t.pnl for t in run.trades
        if t.side == "sell" and t.pnl is not None
    ]

    # Determine period hours from timeframe
    timeframe_hours = {"1h": 1.0, "4h": 4.0, "1d": 24.0}.get(run.timeframe, 1.0)

    # Compute risk metrics
    result = compute_risk_metrics(
        equity_values=equity_values,
        equity_timestamps=equity_timestamps,
        trade_pnls=trade_pnls,
        initial_equity=initial_equity,
        period_hours=timeframe_hours,
    )

    logger.info(
        "risk_metrics_computed",
        run_id=run_id,
        user_id=user_id,
        num_equity_points=len(equity_values),
        num_trades=len(trade_pnls),
    )

    return RiskMetricsResponse(
        run_id=run.id,
        sharpe_ratio=result.sharpe_ratio,
        sortino_ratio=result.sortino_ratio,
        calmar_ratio=result.calmar_ratio,
        total_return_pct=result.total_return_pct,
        annualized_return_pct=result.annualized_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        avg_drawdown_pct=result.avg_drawdown_pct,
        var_95=result.var_95,
        var_99=result.var_99,
        cvar_95=result.cvar_95,
        cvar_99=result.cvar_99,
        num_trades=result.num_trades,
        win_rate=result.win_rate,
        profit_factor=result.profit_factor,
        avg_win=result.avg_win,
        avg_loss=result.avg_loss,
        largest_win=result.largest_win,
        largest_loss=result.largest_loss,
        avg_trade_pnl=result.avg_trade_pnl,
        initial_equity=result.initial_equity,
        final_equity=result.final_equity,
    )


@router.get("/{run_id}", response_model=BacktestRunDetail)
def get_backtest(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get a single backtest run by id with trades, equity curve, and metrics (Phase 7.2)."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )
    run = (
        db.query(BacktestRun)
        .options(
            joinedload(BacktestRun.trades),
            joinedload(BacktestRun.equity_snapshots),
            joinedload(BacktestRun.metrics),
        )
        .filter(BacktestRun.id == run_uuid, BacktestRun.user_id == user_id)
        .first()
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )
    trades = [TradeOut.model_validate(t) for t in run.trades]
    equity_snapshots = sorted(run.equity_snapshots, key=lambda s: s.timestamp)
    equity_curve = [
        EquityPointOut(timestamp=s.timestamp, equity_value=s.equity_value)
        for s in equity_snapshots
    ]
    # For completed runs with no equity snapshots (e.g. no trades), return minimal flat curve
    if run.status == "completed" and not equity_curve:
        initial_value = 10_000.0
        if run.metrics and isinstance(run.metrics.metrics, dict):
            initial_value = float(run.metrics.metrics.get("final_equity", initial_value))
        equity_curve = [
            EquityPointOut(timestamp=run.start_time, equity_value=initial_value),
            EquityPointOut(timestamp=run.end_time, equity_value=initial_value),
        ]
    metrics = run.metrics.metrics if run.metrics else None
    return BacktestRunDetail(
        id=run.id,
        symbol_id=run.symbol_id,
        timeframe=run.timeframe,
        status=run.status,
        start_time=run.start_time,
        end_time=run.end_time,
        created_at=run.created_at,
        error_message=run.error_message,
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
    )
