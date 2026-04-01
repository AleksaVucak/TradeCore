"""Walk-forward validation helpers (Phase 14.1)."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from app.schemas.strategy_config import RsiMaConfig
from app.services.backtest.engine import run_backtest_rsi_ma
from app.services.backtest.metrics import compute_metrics_from_result
from app.services.backtest.types import BacktestCandle


@dataclass(frozen=True)
class WalkForwardWindowResult:
    """Validation result for one rolling candle window."""

    window_index: int
    start_time: object
    end_time: object
    num_candles: int
    num_trades: int
    initial_equity: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float


@dataclass(frozen=True)
class WalkForwardSummary:
    """Aggregate stats across all validation windows."""

    total_windows: int
    window_bars: int
    step_bars: int
    profitable_windows: int
    profitable_window_pct: float
    avg_total_return_pct: float
    best_total_return_pct: float
    worst_total_return_pct: float
    avg_max_drawdown_pct: float
    avg_sharpe_ratio: float


@dataclass(frozen=True)
class WalkForwardValidationResult:
    """Top-level walk-forward validation output."""

    windows: list[WalkForwardWindowResult]
    summary: WalkForwardSummary


def run_walk_forward_validation(
    candles: list[BacktestCandle],
    config: RsiMaConfig,
    *,
    initial_equity: float,
    window_bars: int,
    step_bars: int,
    period_hours: float,
) -> WalkForwardValidationResult:
    """Run the same strategy over multiple rolling candle windows."""
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if window_bars < 2:
        raise ValueError("window_bars must be at least 2")
    if step_bars < 1:
        raise ValueError("step_bars must be at least 1")
    if len(candles) < window_bars:
        raise ValueError("Not enough candles for the requested window size")

    windows: list[WalkForwardWindowResult] = []
    start_idx = 0

    while start_idx + window_bars <= len(candles):
        window_candles = candles[start_idx : start_idx + window_bars]
        result = run_backtest_rsi_ma(
            window_candles,
            config,
            initial_equity=initial_equity,
        )
        metrics = compute_metrics_from_result(result, period_hours=period_hours)
        windows.append(
            WalkForwardWindowResult(
                window_index=len(windows) + 1,
                start_time=window_candles[0].timestamp,
                end_time=window_candles[-1].timestamp,
                num_candles=len(window_candles),
                num_trades=int(metrics.get("num_trades", 0)),
                initial_equity=result.initial_equity,
                final_equity=result.final_equity,
                total_return_pct=float(metrics.get("total_return_pct", 0.0)),
                max_drawdown_pct=float(metrics.get("max_drawdown_pct", 0.0)),
                sharpe_ratio=float(metrics.get("sharpe_ratio", 0.0)),
            )
        )
        start_idx += step_bars

    returns = [window.total_return_pct for window in windows]
    drawdowns = [window.max_drawdown_pct for window in windows]
    sharpes = [window.sharpe_ratio for window in windows]
    profitable_windows = sum(1 for value in returns if value > 0)

    return WalkForwardValidationResult(
        windows=windows,
        summary=WalkForwardSummary(
            total_windows=len(windows),
            window_bars=window_bars,
            step_bars=step_bars,
            profitable_windows=profitable_windows,
            profitable_window_pct=round((profitable_windows / len(windows)) * 100.0, 2),
            avg_total_return_pct=round(mean(returns), 4),
            best_total_return_pct=round(max(returns), 4),
            worst_total_return_pct=round(min(returns), 4),
            avg_max_drawdown_pct=round(mean(drawdowns), 4),
            avg_sharpe_ratio=round(mean(sharpes), 4),
        ),
    )
