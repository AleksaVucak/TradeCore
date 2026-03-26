"""
Advanced risk metrics for backtest results (Phase 12.2).

Computes Sortino ratio, Calmar ratio, VaR, CVaR, and detailed trade statistics
from equity curve and trades data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RiskMetricsResult:
    """Container for all computed risk metrics."""

    # Risk-adjusted returns
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Return metrics
    total_return_pct: float
    annualized_return_pct: float

    # Drawdown metrics
    max_drawdown_pct: float
    avg_drawdown_pct: float

    # Value at Risk (as negative percentages representing potential loss)
    var_95: float
    var_99: float
    cvar_95: float  # Expected Shortfall
    cvar_99: float

    # Trade statistics
    num_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    avg_trade_pnl: float

    # Equity stats
    initial_equity: float
    final_equity: float

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "avg_drawdown_pct": self.avg_drawdown_pct,
            "var_95": self.var_95,
            "var_99": self.var_99,
            "cvar_95": self.cvar_95,
            "cvar_99": self.cvar_99,
            "num_trades": self.num_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "avg_trade_pnl": self.avg_trade_pnl,
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
        }


def _compute_returns(equity_values: list[float]) -> list[float]:
    """Compute period-over-period returns from equity values."""
    if len(equity_values) < 2:
        return []
    returns = []
    for i in range(1, len(equity_values)):
        prev = equity_values[i - 1]
        curr = equity_values[i]
        if prev > 0:
            returns.append((curr - prev) / prev)
        else:
            returns.append(0.0)
    return returns


def _compute_drawdowns(equity_values: list[float]) -> list[float]:
    """Compute drawdown series from equity values (as positive percentages)."""
    if not equity_values:
        return []
    drawdowns = []
    peak = equity_values[0]
    for val in equity_values:
        if val > peak:
            peak = val
        dd_pct = ((peak - val) / peak * 100.0) if peak > 0 else 0.0
        drawdowns.append(dd_pct)
    return drawdowns


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute percentile from sorted values (ascending)."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = (pct / 100.0) * (n - 1)
    lower = int(idx)
    upper = min(lower + 1, n - 1)
    frac = idx - lower
    return sorted_values[lower] * (1 - frac) + sorted_values[upper] * frac


def compute_risk_metrics(
    equity_values: list[float],
    equity_timestamps: list[datetime],
    trade_pnls: list[float],
    initial_equity: float,
    period_hours: float = 1.0,
) -> RiskMetricsResult:
    """
    Compute comprehensive risk metrics from equity curve and trade P&Ls.

    Args:
        equity_values: List of equity values over time (sorted chronologically).
        equity_timestamps: Corresponding timestamps for equity values.
        trade_pnls: List of realized P&L values from closed trades.
        initial_equity: Starting equity value.
        period_hours: Hours per period (1.0 for 1h candles, 4.0 for 4h, etc.).

    Returns:
        RiskMetricsResult with all computed metrics.
    """
    # Handle edge cases
    if not equity_values or initial_equity <= 0:
        return RiskMetricsResult(
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            total_return_pct=0.0,
            annualized_return_pct=0.0,
            max_drawdown_pct=0.0,
            avg_drawdown_pct=0.0,
            var_95=0.0,
            var_99=0.0,
            cvar_95=0.0,
            cvar_99=0.0,
            num_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            avg_trade_pnl=0.0,
            initial_equity=initial_equity,
            final_equity=initial_equity,
        )

    final_equity = equity_values[-1] if equity_values else initial_equity

    # Total return
    total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100.0

    # Annualized return
    annualized_return_pct = 0.0
    if len(equity_timestamps) >= 2 and final_equity > 0:
        delta = equity_timestamps[-1] - equity_timestamps[0]
        years = delta.total_seconds() / (365.25 * 24 * 3600)
        if years > 0 and initial_equity > 0:
            annualized_return_pct = (
                math.pow(final_equity / initial_equity, 1.0 / years) - 1.0
            ) * 100.0

    # Compute returns
    returns = _compute_returns(equity_values)

    # Sharpe ratio
    sharpe_ratio = 0.0
    if returns:
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std = math.sqrt(variance) if variance > 0 else 0.0
        if std > 0:
            periods_per_year = (365.25 * 24) / period_hours
            sharpe_ratio = (mean_ret / std) * math.sqrt(periods_per_year)

    # Sortino ratio (only penalizes downside deviation)
    sortino_ratio = 0.0
    if returns:
        mean_ret = sum(returns) / len(returns)
        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_variance = sum(r**2 for r in downside_returns) / len(returns)
            downside_std = math.sqrt(downside_variance) if downside_variance > 0 else 0.0
            if downside_std > 0:
                periods_per_year = (365.25 * 24) / period_hours
                sortino_ratio = (mean_ret / downside_std) * math.sqrt(periods_per_year)

    # Drawdown metrics
    drawdowns = _compute_drawdowns(equity_values)
    max_drawdown_pct = max(drawdowns) if drawdowns else 0.0
    avg_drawdown_pct = sum(drawdowns) / len(drawdowns) if drawdowns else 0.0

    # Calmar ratio (annualized return / max drawdown)
    calmar_ratio = 0.0
    if max_drawdown_pct > 0:
        calmar_ratio = annualized_return_pct / max_drawdown_pct

    # VaR and CVaR (on returns, expressed as percentage)
    var_95 = 0.0
    var_99 = 0.0
    cvar_95 = 0.0
    cvar_99 = 0.0

    if returns:
        sorted_returns = sorted(returns)
        n = len(sorted_returns)

        # VaR: the return at the given percentile (5th percentile for 95% VaR)
        var_95_idx = int(0.05 * n)
        var_99_idx = int(0.01 * n)

        var_95 = sorted_returns[var_95_idx] * 100.0 if var_95_idx < n else 0.0
        var_99 = sorted_returns[var_99_idx] * 100.0 if var_99_idx < n else 0.0

        # CVaR (Expected Shortfall): average of returns below VaR threshold
        tail_95 = sorted_returns[: max(1, var_95_idx + 1)]
        tail_99 = sorted_returns[: max(1, var_99_idx + 1)]

        cvar_95 = (sum(tail_95) / len(tail_95)) * 100.0 if tail_95 else 0.0
        cvar_99 = (sum(tail_99) / len(tail_99)) * 100.0 if tail_99 else 0.0

    # Trade statistics
    num_trades = len(trade_pnls)
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p <= 0]

    win_rate = (len(wins) / num_trades * 100.0) if num_trades > 0 else 0.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
        gross_profit if gross_profit > 0 else 0.0
    )

    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0

    largest_win = max(wins) if wins else 0.0
    largest_loss = min(losses) if losses else 0.0

    avg_trade_pnl = (sum(trade_pnls) / num_trades) if num_trades > 0 else 0.0

    return RiskMetricsResult(
        sharpe_ratio=round(sharpe_ratio, 4),
        sortino_ratio=round(sortino_ratio, 4),
        calmar_ratio=round(calmar_ratio, 4),
        total_return_pct=round(total_return_pct, 4),
        annualized_return_pct=round(annualized_return_pct, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        avg_drawdown_pct=round(avg_drawdown_pct, 4),
        var_95=round(var_95, 4),
        var_99=round(var_99, 4),
        cvar_95=round(cvar_95, 4),
        cvar_99=round(cvar_99, 4),
        num_trades=num_trades,
        win_rate=round(win_rate, 2),
        profit_factor=round(profit_factor, 4),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        largest_win=round(largest_win, 2),
        largest_loss=round(largest_loss, 2),
        avg_trade_pnl=round(avg_trade_pnl, 2),
        initial_equity=round(initial_equity, 2),
        final_equity=round(final_equity, 2),
    )
