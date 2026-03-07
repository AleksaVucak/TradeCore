"""
Feature engineering for ML regime classification (Phase 9.1).

Pure-Python module that computes rolling features from OHLCV candle data.
All functions accept plain lists/sequences and return aligned lists (same
length as input, with None for bars before the lookback window is filled).

Features provided:
  - rolling_returns: log returns over a rolling window
  - rolling_volatility: std dev of log returns over a rolling window
  - atr: Average True Range (Wilder smoothing)
  - momentum: price change over N bars as a percentage
  - rolling_volume_ratio: volume / rolling average volume
  - rsi: RSI (re-exported from backtest indicators for convenience)
  - sma: SMA (re-exported from backtest indicators for convenience)
  - bollinger_band_width: (upper - lower) / middle Bollinger Band width
  - compute_feature_matrix: convenience function to compute all features at once
"""

from __future__ import annotations

import math
from typing import Sequence

from app.services.backtest.indicators import rsi, sma


def log_returns(closes: Sequence[float]) -> list[float | None]:
    """
    Per-bar log return: ln(close[i] / close[i-1]).

    Returns None for the first bar.
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    for i in range(1, n):
        if closes[i - 1] > 0 and closes[i] > 0:
            out[i] = math.log(closes[i] / closes[i - 1])
        else:
            out[i] = 0.0
    return out


def rolling_returns(closes: Sequence[float], period: int) -> list[float | None]:
    """
    Rolling cumulative log return over `period` bars.

    rolling_return[i] = ln(close[i] / close[i - period]).
    Returns None for i < period.
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if period < 1:
        return out
    for i in range(period, n):
        if closes[i - period] > 0 and closes[i] > 0:
            out[i] = math.log(closes[i] / closes[i - period])
        else:
            out[i] = 0.0
    return out


def rolling_volatility(closes: Sequence[float], period: int) -> list[float | None]:
    """
    Rolling standard deviation of per-bar log returns over `period` bars.

    Requires period >= 2. Returns None for i < period.
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if period < 2 or n <= period:
        return out

    lr = log_returns(closes)

    for i in range(period, n):
        window = [lr[j] for j in range(i - period + 1, i + 1) if lr[j] is not None]
        if len(window) < 2:
            out[i] = 0.0
            continue
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
        out[i] = math.sqrt(variance)
    return out


def true_range(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> list[float | None]:
    """
    True Range per bar.

    TR[i] = max(high[i] - low[i], |high[i] - close[i-1]|, |low[i] - close[i-1]|).
    Returns None for bar 0.
    """
    n = len(highs)
    out: list[float | None] = [None] * n
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        out[i] = max(hl, hc, lc)
    return out


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float | None]:
    """
    Average True Range using Wilder's smoothing.

    Returns None for bars before index `period`.
    """
    n = len(highs)
    out: list[float | None] = [None] * n
    if period < 1 or n <= period:
        return out

    tr = true_range(highs, lows, closes)

    first_sum = 0.0
    for i in range(1, period + 1):
        first_sum += tr[i] if tr[i] is not None else 0.0
    current_atr = first_sum / period
    out[period] = current_atr

    for i in range(period + 1, n):
        tr_val = tr[i] if tr[i] is not None else 0.0
        current_atr = (current_atr * (period - 1) + tr_val) / period
        out[i] = current_atr

    return out


def momentum(closes: Sequence[float], period: int) -> list[float | None]:
    """
    Price momentum as percentage change over `period` bars.

    momentum[i] = (close[i] - close[i - period]) / close[i - period] * 100.
    Returns None for i < period.
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if period < 1:
        return out
    for i in range(period, n):
        if closes[i - period] != 0:
            out[i] = (closes[i] - closes[i - period]) / closes[i - period] * 100.0
        else:
            out[i] = 0.0
    return out


def rolling_volume_ratio(
    volumes: Sequence[float], period: int
) -> list[float | None]:
    """
    Volume relative to its rolling average: volume[i] / SMA(volume, period).

    Values > 1.0 mean above-average volume. Returns None for i < period - 1.
    """
    n = len(volumes)
    out: list[float | None] = [None] * n
    if period < 1 or n < period:
        return out

    vol_sma = sma(list(volumes), period)
    for i in range(n):
        if vol_sma[i] is not None and vol_sma[i] > 0:
            out[i] = volumes[i] / vol_sma[i]
    return out


def bollinger_band_width(
    closes: Sequence[float], period: int = 20, num_std: float = 2.0
) -> list[float | None]:
    """
    Bollinger Band width: (upper - lower) / middle.

    width = 2 * num_std * rolling_std / SMA.
    Returns None for i < period - 1.
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if period < 2 or n < period:
        return out

    mid = sma(list(closes), period)

    for i in range(period - 1, n):
        if mid[i] is None or mid[i] == 0:
            continue
        window = closes[i - period + 1 : i + 1]
        mean = mid[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(variance)
        out[i] = (2.0 * num_std * std) / mean

    return out


FeatureRow = dict[str, float | None]


def compute_feature_matrix(
    *,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    rsi_period: int = 14,
    ma_period: int = 20,
    atr_period: int = 14,
    vol_period: int = 20,
    momentum_period: int = 10,
    volume_ratio_period: int = 20,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> list[FeatureRow]:
    """
    Compute all features for a series of OHLCV bars and return a list of
    dicts (one per bar). Bars before the warmup window have None values.

    Features computed:
      - log_return: single-bar log return
      - rolling_return_{vol_period}: cumulative log return over vol_period bars
      - volatility_{vol_period}: rolling std dev of log returns
      - atr_{atr_period}: Average True Range
      - momentum_{momentum_period}: % price change over momentum_period bars
      - rsi_{rsi_period}: RSI
      - sma_{ma_period}: simple moving average
      - volume_ratio_{volume_ratio_period}: volume / SMA(volume)
      - bb_width_{bb_period}: Bollinger Band width
    """
    n = len(closes)

    feat_log_return = log_returns(closes)
    feat_rolling_return = rolling_returns(closes, vol_period)
    feat_volatility = rolling_volatility(closes, vol_period)
    feat_atr = atr(highs, lows, closes, atr_period)
    feat_momentum = momentum(closes, momentum_period)
    feat_rsi = rsi(closes, rsi_period)
    feat_sma = sma(list(closes), ma_period)
    feat_volume_ratio = rolling_volume_ratio(volumes, volume_ratio_period)
    feat_bb_width = bollinger_band_width(closes, bb_period, bb_std)

    rows: list[FeatureRow] = []
    for i in range(n):
        rows.append({
            "log_return": feat_log_return[i],
            f"rolling_return_{vol_period}": feat_rolling_return[i],
            f"volatility_{vol_period}": feat_volatility[i],
            f"atr_{atr_period}": feat_atr[i],
            f"momentum_{momentum_period}": feat_momentum[i],
            f"rsi_{rsi_period}": feat_rsi[i],
            f"sma_{ma_period}": feat_sma[i],
            f"volume_ratio_{volume_ratio_period}": feat_volume_ratio[i],
            f"bb_width_{bb_period}": feat_bb_width[i],
        })
    return rows
