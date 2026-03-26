"""
Buy-and-hold benchmark computation for backtest comparison (Phase 12.4).

Computes what the equity curve would look like if you simply bought
at the start and held through the end, using the same initial capital.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class BenchmarkPoint:
    """Single point on the benchmark equity curve."""

    timestamp: datetime
    equity_value: float


@dataclass
class BenchmarkResult:
    """Result of buy-and-hold benchmark computation."""

    equity_curve: list[BenchmarkPoint]
    initial_equity: float
    final_equity: float
    total_return_pct: float
    alpha_pct: float  # Strategy return - benchmark return

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "equity_curve": [
                {"timestamp": p.timestamp.isoformat(), "equity_value": p.equity_value}
                for p in self.equity_curve
            ],
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
            "total_return_pct": self.total_return_pct,
            "alpha_pct": self.alpha_pct,
        }


def compute_benchmark(
    candle_closes: list[tuple[datetime, float]],
    initial_equity: float,
    strategy_return_pct: float,
) -> BenchmarkResult:
    """
    Compute buy-and-hold benchmark equity curve.

    Args:
        candle_closes: List of (timestamp, close_price) tuples, sorted chronologically.
        initial_equity: Starting equity (same as backtest).
        strategy_return_pct: The strategy's total return percentage (for alpha calc).

    Returns:
        BenchmarkResult with equity curve and summary metrics.
    """
    if not candle_closes or initial_equity <= 0:
        return BenchmarkResult(
            equity_curve=[],
            initial_equity=initial_equity,
            final_equity=initial_equity,
            total_return_pct=0.0,
            alpha_pct=strategy_return_pct,
        )

    # Buy at first close price
    first_price = candle_closes[0][1]
    if first_price <= 0:
        return BenchmarkResult(
            equity_curve=[],
            initial_equity=initial_equity,
            final_equity=initial_equity,
            total_return_pct=0.0,
            alpha_pct=strategy_return_pct,
        )

    # Number of shares we can buy
    shares = initial_equity / first_price

    # Build equity curve: equity = shares * price at each point
    equity_curve: list[BenchmarkPoint] = []
    for ts, price in candle_closes:
        equity_value = shares * price
        equity_curve.append(BenchmarkPoint(timestamp=ts, equity_value=round(equity_value, 2)))

    final_equity = equity_curve[-1].equity_value if equity_curve else initial_equity
    total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100.0

    # Alpha = strategy return - benchmark return
    alpha_pct = strategy_return_pct - total_return_pct

    return BenchmarkResult(
        equity_curve=equity_curve,
        initial_equity=round(initial_equity, 2),
        final_equity=round(final_equity, 2),
        total_return_pct=round(total_return_pct, 4),
        alpha_pct=round(alpha_pct, 4),
    )
