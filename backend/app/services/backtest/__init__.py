"""
Backtest service (Phase 6.1+).

Synchronous engine: signal generation + execution loop with fees/slippage.
Metrics module: return, drawdown, win rate, Sharpe (Phase 6.2).
"""

from app.services.backtest.engine import run_backtest_rsi_ma
from app.services.backtest.metrics import compute_metrics, compute_metrics_from_result
from app.services.backtest.types import (
    BacktestCandle,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)

__all__ = [
    "run_backtest_rsi_ma",
    "compute_metrics",
    "compute_metrics_from_result",
    "BacktestCandle",
    "BacktestResult",
    "BacktestTrade",
    "EquityPoint",
]
