"""
Backtest service (Phase 6.1+).

Synchronous engine: signal generation + execution loop with fees/slippage.
Metrics module: return, drawdown, win rate, Sharpe (Phase 6.2).
"""

from app.services.backtest.engine import run_backtest_rsi_ma
from app.services.backtest.metrics import compute_metrics, compute_metrics_from_result
from app.services.backtest.ml_engine import run_backtest_ml_signal
from app.services.backtest.types import (
    BacktestCandle,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)
from app.services.backtest.walk_forward import run_walk_forward_validation

__all__ = [
    "run_backtest_rsi_ma",
    "run_backtest_ml_signal",
    "compute_metrics",
    "compute_metrics_from_result",
    "run_walk_forward_validation",
    "BacktestCandle",
    "BacktestResult",
    "BacktestTrade",
    "EquityPoint",
]
