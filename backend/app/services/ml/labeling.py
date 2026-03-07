"""
Heuristic regime labeling for ML training (Phase 9.2).

Labels each bar as one of: "trend", "range", or "high_vol" based on
forward-looking returns and volatility over a rolling window.

This is a rules-based labeling function used to generate ground-truth labels
for supervised training. In production you might replace this with
human-labeled data or a more sophisticated approach.
"""

from __future__ import annotations

import math
from typing import Sequence

REGIME_TREND = "trend"
REGIME_RANGE = "range"
REGIME_HIGH_VOL = "high_vol"

VALID_REGIMES = {REGIME_TREND, REGIME_RANGE, REGIME_HIGH_VOL}


def label_regimes(
    closes: Sequence[float],
    *,
    window: int = 20,
    trend_threshold: float = 0.03,
    vol_threshold_pct: float = 75.0,
) -> list[str | None]:
    """
    Assign a regime label to each bar using a forward-looking heuristic.

    For each bar i, we look at the next `window` bars and compute:
      - forward_return = ln(close[i+window] / close[i])
      - forward_volatility = std dev of per-bar log returns in [i..i+window]

    Then we classify:
      - "high_vol" if forward_volatility is in the top `vol_threshold_pct`
        percentile of all computed volatilities.
      - "trend" if |forward_return| >= `trend_threshold` (and not high_vol).
      - "range" otherwise.

    Returns None for the last `window` bars (no forward data available).

    Args:
        closes: closing prices, sorted chronologically.
        window: forward-looking window size in bars.
        trend_threshold: absolute log-return threshold for "trend".
        vol_threshold_pct: percentile (0–100) above which volatility
            is considered "high_vol".
    """
    n = len(closes)
    labels: list[str | None] = [None] * n
    if n <= window or window < 2:
        return labels

    forward_returns: list[float] = []
    forward_vols: list[float] = []
    indices: list[int] = []

    for i in range(n - window):
        if closes[i] <= 0 or closes[i + window] <= 0:
            forward_returns.append(0.0)
            forward_vols.append(0.0)
            indices.append(i)
            continue

        fwd_ret = math.log(closes[i + window] / closes[i])

        log_rets = []
        for j in range(i, i + window):
            if closes[j] > 0 and closes[j + 1] > 0:
                log_rets.append(math.log(closes[j + 1] / closes[j]))
            else:
                log_rets.append(0.0)
        mean_lr = sum(log_rets) / len(log_rets)
        variance = sum((x - mean_lr) ** 2 for x in log_rets) / (len(log_rets) - 1)
        fwd_vol = math.sqrt(variance)

        forward_returns.append(fwd_ret)
        forward_vols.append(fwd_vol)
        indices.append(i)

    if not forward_vols:
        return labels

    sorted_vols = sorted(forward_vols)
    pct_idx = int(len(sorted_vols) * vol_threshold_pct / 100.0)
    pct_idx = min(pct_idx, len(sorted_vols) - 1)
    vol_cutoff = sorted_vols[pct_idx]

    for k, i in enumerate(indices):
        fwd_vol = forward_vols[k]
        fwd_ret = forward_returns[k]

        if fwd_vol > vol_cutoff:
            labels[i] = REGIME_HIGH_VOL
        elif abs(fwd_ret) >= trend_threshold:
            labels[i] = REGIME_TREND
        else:
            labels[i] = REGIME_RANGE

    return labels
