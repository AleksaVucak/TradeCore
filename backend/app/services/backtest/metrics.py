"""
Metrics module for backtest results (Phase 6.2).

Computes return, drawdown, win rate, Sharpe ratio, etc. from trades and equity curve.
All outputs are JSON-serializable for storage in MetricSnapshot (JSONB).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.backtest.types import BacktestResult, BacktestTrade, EquityPoint


def compute_metrics(
    trades: list["BacktestTrade"],
    equity_curve: list["EquityPoint"],
    initial_equity: float,
    *,
    period_hours: float = 1.0,
) -> dict[str, float | int]:
    """
    Compute performance metrics from backtest trades and equity curve.

    Args:
        trades: List of BacktestTrade (only sell trades have pnl set).
        equity_curve: List of EquityPoint (timestamp, equity_value), sorted by time.
        initial_equity: Starting equity.
        period_hours: Assumed bar period in hours (e.g. 1.0 for 1h, 4.0 for 4h).
                      Used to annualize return and Sharpe.

    Returns:
        Dict of metric name -> value (floats/ints), suitable for JSONB storage.
    """
    result: dict[str, float | int] = {}

    if initial_equity <= 0:
        result["total_return"] = 0.0
        result["total_return_pct"] = 0.0
        result["annualized_return_pct"] = 0.0
        result["max_drawdown"] = 0.0
        result["max_drawdown_pct"] = 0.0
        result["num_trades"] = 0
        result["num_wins"] = 0
        result["num_losses"] = 0
        result["win_rate"] = 0.0
        result["profit_factor"] = 0.0
        result["sharpe_ratio"] = 0.0
        result["final_equity"] = 0.0
        return result

    final_equity = initial_equity
    if equity_curve:
        final_equity = equity_curve[-1].equity_value

    total_return = final_equity - initial_equity
    total_return_pct = (total_return / initial_equity) * 100.0
    result["total_return"] = round(total_return, 6)
    result["total_return_pct"] = round(total_return_pct, 4)
    result["final_equity"] = round(final_equity, 6)

    # Annualized return: need time span
    annualized_return_pct = 0.0
    if equity_curve and len(equity_curve) >= 2 and initial_equity > 0 and final_equity > 0:
        first_ts = equity_curve[0].timestamp
        last_ts = equity_curve[-1].timestamp
        delta = last_ts - first_ts
        years = delta.total_seconds() / (365.25 * 24 * 3600)
        if years > 0:
            annualized_return_pct = (math.pow(final_equity / initial_equity, 1.0 / years) - 1.0) * 100.0
    result["annualized_return_pct"] = round(annualized_return_pct, 4)

    # Max drawdown from equity curve
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    peak = initial_equity
    for point in equity_curve:
        if point.equity_value > peak:
            peak = point.equity_value
        dd = peak - point.equity_value
        if dd > max_drawdown:
            max_drawdown = dd
        if peak > 0:
            dd_pct = (dd / peak) * 100.0
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct
    result["max_drawdown"] = round(max_drawdown, 6)
    result["max_drawdown_pct"] = round(max_drawdown_pct, 4)

    # Closed trades only (sells with pnl)
    closed = [t for t in trades if t.side == "sell" and t.pnl is not None]
    num_trades = len(closed)
    result["num_trades"] = num_trades

    num_wins = sum(1 for t in closed if t.pnl is not None and t.pnl > 0)
    num_losses = sum(1 for t in closed if t.pnl is not None and t.pnl <= 0)
    result["num_wins"] = num_wins
    result["num_losses"] = num_losses
    result["win_rate"] = round((num_wins / num_trades * 100.0) if num_trades else 0.0, 2)

    gross_profit = sum(t.pnl for t in closed if t.pnl is not None and t.pnl > 0)
    gross_loss = sum(-t.pnl for t in closed if t.pnl is not None and t.pnl < 0)
    result["profit_factor"] = round(
        (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0),
        4,
    )

    # Sharpe ratio: period returns from equity curve, then annualize
    sharpe_ratio = 0.0
    if len(equity_curve) >= 2:
        returns: list[float] = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1].equity_value
            curr = equity_curve[i].equity_value
            if prev > 0:
                returns.append((curr - prev) / prev)
        if returns:
            n = len(returns)
            mean_ret = sum(returns) / n
            variance = sum((r - mean_ret) ** 2 for r in returns) / n if n else 0
            std = variance ** 0.5
            if std > 0:
                # Periods per year: e.g. 1h bars -> 8760
                periods_per_year = (365.25 * 24) / period_hours
                sharpe_ratio = (mean_ret / std) * (periods_per_year ** 0.5)
    result["sharpe_ratio"] = round(sharpe_ratio, 4)

    return result


def compute_metrics_from_result(
    result: "BacktestResult",
    *,
    period_hours: float = 1.0,
) -> dict[str, float | int]:
    """
    Compute metrics from a BacktestResult (convenience wrapper).
    """
    return compute_metrics(
        trades=result.trades,
        equity_curve=result.equity_curve,
        initial_equity=result.initial_equity,
        period_hours=period_hours,
    )
