"""
Monte Carlo robustness analysis for completed backtests (Phase 14.3).

Resamples closed-trade P&L sequences to estimate distribution of outcomes when
trade order (shuffle) or trade outcomes (bootstrap) vary.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

MonteCarloMethod = Literal["bootstrap", "shuffle"]


def _percentile_linear(sorted_values: list[float], p: float) -> float:
    """Linear interpolation percentile; p in [0, 100]."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    s = sorted_values
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (k - f) * (s[c] - s[f])


def _max_drawdown_pct_from_equity(equity_path: list[float]) -> float:
    """Max drawdown as percentage of running peak (non-negative)."""
    if not equity_path:
        return 0.0
    peak = equity_path[0]
    max_dd = 0.0
    for eq in equity_path:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _equity_path_from_pnls(initial_equity: float, pnls: list[float]) -> list[float]:
    """Cumulative equity after each closed trade P&L."""
    path = [initial_equity]
    eq = initial_equity
    for p in pnls:
        eq += p
        path.append(eq)
    return path


def _total_return_pct(initial_equity: float, final_equity: float) -> float:
    if initial_equity <= 0:
        return 0.0
    return (final_equity - initial_equity) / initial_equity * 100.0


@dataclass(frozen=True)
class EquityPercentilePoint:
    step_index: int
    p5_equity: float
    p50_equity: float
    p95_equity: float


@dataclass(frozen=True)
class MonteCarloResult:
    method: MonteCarloMethod
    num_simulations: int
    num_closed_trades: int
    initial_equity: float
    seed: int | None

    mean_final_equity: float
    median_final_equity: float
    p5_final_equity: float
    p95_final_equity: float
    best_final_equity: float
    worst_final_equity: float

    mean_total_return_pct: float
    median_total_return_pct: float
    p5_total_return_pct: float
    p95_total_return_pct: float
    best_total_return_pct: float
    worst_total_return_pct: float

    mean_max_drawdown_pct: float
    median_max_drawdown_pct: float
    p95_max_drawdown_pct: float
    worst_max_drawdown_pct: float

    probability_profit_pct: float
    probability_loss_pct: float
    probability_drawdown_gt_10_pct: float

    original_total_return_pct: float | None
    percentile_equity_band: list[EquityPercentilePoint]


def compute_monte_carlo(
    *,
    closed_trade_pnls: list[float],
    initial_equity: float,
    num_simulations: int,
    method: MonteCarloMethod,
    seed: int | None,
    original_total_return_pct: float | None,
    max_band_points: int = 200,
) -> MonteCarloResult:
    """
    Run Monte Carlo simulations on closed-trade P&L values.

    ``closed_trade_pnls`` should be in chronological order (used as the pool
    for bootstrap; shuffle randomizes order only).
    """
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if num_simulations < 50:
        raise ValueError("num_simulations must be at least 50")
    if num_simulations > 10_000:
        raise ValueError("num_simulations must be at most 10000")
    if len(closed_trade_pnls) < 2:
        raise ValueError(
            "Monte Carlo requires at least 2 closed trades with realized P&L"
        )

    rng = random.Random(seed) if seed is not None else random.Random()

    n = len(closed_trade_pnls)
    final_equities: list[float] = []
    total_returns: list[float] = []
    max_drawdowns: list[float] = []

    # For percentile band: collect equity at each step across sims
    # steps 0..n (inclusive)
    band_steps = n + 1
    if band_steps > max_band_points:
        indices = sorted(
            {int(round(i * (band_steps - 1) / (max_band_points - 1))) for i in range(max_band_points)}
        )
    else:
        indices = list(range(band_steps))

    # Store per-step values only for selected indices (memory-friendly)
    step_to_values: dict[int, list[float]] = {i: [] for i in indices}

    for _ in range(num_simulations):
        if method == "shuffle":
            seq = closed_trade_pnls.copy()
            rng.shuffle(seq)
        else:
            seq = [rng.choice(closed_trade_pnls) for _ in range(n)]

        path = _equity_path_from_pnls(initial_equity, seq)
        final_eq = path[-1]
        final_equities.append(final_eq)
        total_returns.append(_total_return_pct(initial_equity, final_eq))
        max_drawdowns.append(_max_drawdown_pct_from_equity(path))

        for i in indices:
            if i < len(path):
                step_to_values[i].append(path[i])

    final_equities.sort()
    total_returns.sort()
    max_drawdowns.sort()

    profiting = sum(1 for e in final_equities if e > initial_equity)
    losing = sum(1 for e in final_equities if e < initial_equity)
    dd_gt_10 = sum(1 for d in max_drawdowns if d > 10.0)

    n_s = float(num_simulations)
    prob_profit = round((profiting / n_s) * 100.0, 2)
    prob_loss = round((losing / n_s) * 100.0, 2)
    prob_dd_10 = round((dd_gt_10 / n_s) * 100.0, 2)

    band: list[EquityPercentilePoint] = []
    for i in sorted(step_to_values.keys()):
        vals = sorted(step_to_values[i])
        band.append(
            EquityPercentilePoint(
                step_index=i,
                p5_equity=round(_percentile_linear(vals, 5.0), 4),
                p50_equity=round(_percentile_linear(vals, 50.0), 4),
                p95_equity=round(_percentile_linear(vals, 95.0), 4),
            )
        )

    return MonteCarloResult(
        method=method,
        num_simulations=num_simulations,
        num_closed_trades=n,
        initial_equity=initial_equity,
        seed=seed,
        mean_final_equity=round(sum(final_equities) / n_s, 4),
        median_final_equity=round(_percentile_linear(final_equities, 50.0), 4),
        p5_final_equity=round(_percentile_linear(final_equities, 5.0), 4),
        p95_final_equity=round(_percentile_linear(final_equities, 95.0), 4),
        best_final_equity=round(max(final_equities), 4),
        worst_final_equity=round(min(final_equities), 4),
        mean_total_return_pct=round(sum(total_returns) / n_s, 4),
        median_total_return_pct=round(_percentile_linear(total_returns, 50.0), 4),
        p5_total_return_pct=round(_percentile_linear(total_returns, 5.0), 4),
        p95_total_return_pct=round(_percentile_linear(total_returns, 95.0), 4),
        best_total_return_pct=round(max(total_returns), 4),
        worst_total_return_pct=round(min(total_returns), 4),
        mean_max_drawdown_pct=round(sum(max_drawdowns) / n_s, 4),
        median_max_drawdown_pct=round(_percentile_linear(max_drawdowns, 50.0), 4),
        p95_max_drawdown_pct=round(_percentile_linear(max_drawdowns, 95.0), 4),
        worst_max_drawdown_pct=round(max(max_drawdowns), 4),
        probability_profit_pct=prob_profit,
        probability_loss_pct=prob_loss,
        probability_drawdown_gt_10_pct=prob_dd_10,
        original_total_return_pct=original_total_return_pct,
        percentile_equity_band=band,
    )
