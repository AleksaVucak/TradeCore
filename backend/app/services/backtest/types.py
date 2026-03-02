"""
Types for the backtest engine (Phase 6.1).

All types are in-memory only; no database dependency.
Candle-like inputs can be built from DB Candle or NormalizedCandle.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BacktestCandle:
    """Single OHLCV bar for backtest input. Timestamp should be timezone-aware (UTC)."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_candle_like(
        cls,
        *,
        timestamp: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> "BacktestCandle":
        """Build from any object with OHLCV + timestamp (e.g. ORM Candle, NormalizedCandle)."""
        return cls(
            timestamp=timestamp,
            open=float(open),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(volume),
        )


@dataclass
class BacktestTrade:
    """One executed trade (buy or sell) from the backtest."""

    timestamp: datetime
    side: str  # "buy" | "sell"
    price: float  # execution price (after slippage)
    quantity: float
    fee: float  # fee in quote currency
    slippage: float  # slippage cost in quote currency
    pnl: float | None  # realized PnL in quote currency; None for opens, set for closes


@dataclass
class EquityPoint:
    """One point on the equity curve."""

    timestamp: datetime
    equity_value: float


@dataclass
class BacktestResult:
    """Result of a synchronous backtest run."""

    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    initial_equity: float
    final_equity: float
