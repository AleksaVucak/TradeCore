"""
Per-regime performance analysis (Phase 9.5).

Joins backtest trades with regime labels to compute performance metrics
broken down by market regime (trend, range, high_vol).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.regime_label import RegimeLabel
from app.models.trade import Trade


REGIME_LABELS = {
    "trend": "Trend",
    "range": "Range",
    "high_vol": "High Volatility",
}

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def _match_trade_to_regime(
    trade_ts: datetime,
    regime_map: dict[datetime, str],
    tolerance_seconds: int,
) -> str | None:
    """
    Find the regime label closest to a trade's timestamp.

    Checks the exact timestamp first, then scans within ±tolerance_seconds.
    """
    if trade_ts in regime_map:
        return regime_map[trade_ts]

    best_regime: str | None = None
    best_diff = float("inf")

    for ts, regime in regime_map.items():
        diff = abs((trade_ts - ts).total_seconds())
        if diff < best_diff and diff <= tolerance_seconds:
            best_diff = diff
            best_regime = regime

    return best_regime


def compute_regime_performance(
    db: Session,
    *,
    run_id: str,
    symbol_id: int,
    timeframe: str,
    start_time: datetime,
    end_time: datetime,
    model_id: int,
) -> dict[str, Any]:
    """
    Compute per-regime performance metrics for a backtest run.

    Joins trades (sell trades with PnL) to regime labels by matching
    timestamps, then aggregates by regime.

    Returns a dict suitable for the RegimePerformanceResponse schema.
    """
    labels = (
        db.query(RegimeLabel)
        .filter(
            RegimeLabel.model_id == model_id,
            RegimeLabel.symbol_id == symbol_id,
            RegimeLabel.timeframe == timeframe,
            RegimeLabel.timestamp >= start_time,
            RegimeLabel.timestamp <= end_time,
        )
        .all()
    )

    regime_map: dict[datetime, str] = {lbl.timestamp: lbl.regime for lbl in labels}
    total_bars = len(labels)

    bar_counts: dict[str, int] = {}
    for regime in regime_map.values():
        bar_counts[regime] = bar_counts.get(regime, 0) + 1

    trades = (
        db.query(Trade)
        .filter(
            Trade.backtest_run_id == run_id,
            Trade.side == "sell",
            Trade.pnl.isnot(None),
        )
        .order_by(Trade.timestamp.asc())
        .all()
    )

    tolerance = TIMEFRAME_SECONDS.get(timeframe, 3600)

    regime_trades: dict[str, list[float]] = {r: [] for r in REGIME_LABELS}
    matched_count = 0

    for trade in trades:
        regime = _match_trade_to_regime(trade.timestamp, regime_map, tolerance)
        if regime is None:
            continue
        matched_count += 1
        if regime not in regime_trades:
            regime_trades[regime] = []
        regime_trades[regime].append(trade.pnl)

    result_regimes = []
    for regime_key in ["trend", "range", "high_vol"]:
        pnls = regime_trades.get(regime_key, [])
        bars = bar_counts.get(regime_key, 0)
        bars_pct = round((bars / total_bars * 100) if total_bars > 0 else 0, 1)
        num_trades = len(pnls)
        total_pnl = round(sum(pnls), 2) if pnls else 0.0
        avg_pnl = round(total_pnl / num_trades, 2) if num_trades > 0 else None
        wins = sum(1 for p in pnls if p >= 0)
        losses = sum(1 for p in pnls if p < 0)
        win_rate = round(wins / num_trades * 100, 1) if num_trades > 0 else None

        result_regimes.append({
            "regime": regime_key,
            "label": REGIME_LABELS[regime_key],
            "bars": bars,
            "bars_pct": bars_pct,
            "num_trades": num_trades,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "win_rate": win_rate,
            "wins": wins,
            "losses": losses,
        })

    return {
        "run_id": run_id,
        "total_bars": total_bars,
        "total_trades_matched": matched_count,
        "regimes": result_regimes,
    }
