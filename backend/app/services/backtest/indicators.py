"""
Technical indicators for backtest signal generation (Phase 6.1).
"""

from typing import Sequence


def sma(closes: Sequence[float], period: int) -> list[float | None]:
    """
    Simple moving average of closing prices.

    Returns a list aligned with `closes`: None for indices before `period - 1`,
    then SMA for the last `period` closes at each index.
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if period < 1 or n < period:
        return out
    window_sum = sum(closes[:period])
    out[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum = window_sum - closes[i - period] + closes[i]
        out[i] = window_sum / period
    return out


def rsi(closes: Sequence[float], period: int) -> list[float | None]:
    """
    RSI (Relative Strength Index) using Wilder's smoothing.

    Returns a list aligned with `closes`: None for indices before the first
    valid RSI (need period+1 closes), then RSI in [0, 100].
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if period < 2 or n <= period:
        return out

    # First average gain/loss: simple average of first `period` gains/losses
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder smoothing: avg_gain = (prev_avg_gain * (period-1) + current_gain) / period
    for i in range(period + 1, n):
        ch = closes[i] - closes[i - 1]
        g = max(ch, 0.0)
        l = max(-ch, 0.0)
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))

    return out
