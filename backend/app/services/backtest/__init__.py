"""
Backtest service (Phase 6.1+).

Synchronous engine: signal generation + execution loop with fees/slippage.
"""

from app.services.backtest.engine import run_backtest_rsi_ma
from app.services.backtest.types import (
    BacktestCandle,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)

__all__ = [
    "run_backtest_rsi_ma",
    "BacktestCandle",
    "BacktestResult",
    "BacktestTrade",
    "EquityPoint",
]
