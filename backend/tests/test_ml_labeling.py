"""Tests for ML heuristic regime labeling (Phase 9.2)."""

import pytest

from app.services.ml.labeling import (
    REGIME_HIGH_VOL,
    REGIME_RANGE,
    REGIME_TREND,
    VALID_REGIMES,
    label_regimes,
)


def _make_uptrend(n: int = 100, start: float = 100.0, step: float = 1.0) -> list[float]:
    return [start + i * step for i in range(n)]


def _make_flat(n: int = 100, price: float = 100.0) -> list[float]:
    return [price] * n


def _make_volatile(n: int = 100, base: float = 100.0, swing: float = 10.0) -> list[float]:
    return [base + swing * (1 if i % 2 == 0 else -1) for i in range(n)]


class TestLabelRegimesBasic:
    def test_returns_correct_length(self) -> None:
        closes = _make_uptrend(100)
        labels = label_regimes(closes)
        assert len(labels) == 100

    def test_tail_bars_are_none(self) -> None:
        closes = _make_uptrend(100)
        labels = label_regimes(closes, window=20)
        for lbl in labels[-20:]:
            assert lbl is None

    def test_labeled_bars_are_valid_regimes(self) -> None:
        closes = _make_uptrend(100)
        labels = label_regimes(closes)
        for lbl in labels:
            assert lbl is None or lbl in VALID_REGIMES

    def test_strong_uptrend_has_trend_labels(self) -> None:
        closes = _make_uptrend(100, step=5.0)
        labels = label_regimes(closes, window=20, trend_threshold=0.01)
        trend_count = sum(1 for lbl in labels if lbl == REGIME_TREND)
        assert trend_count > 0

    def test_flat_market_has_range_labels(self) -> None:
        closes = _make_flat(100)
        labels = label_regimes(closes, window=10, trend_threshold=0.05)
        range_count = sum(1 for lbl in labels if lbl == REGIME_RANGE)
        non_none = sum(1 for lbl in labels if lbl is not None)
        assert range_count == non_none

    def test_volatile_market_has_high_vol_labels(self) -> None:
        closes = [100.0 + (i * 3 if i % 4 < 2 else -i * 2) for i in range(150)]
        labels = label_regimes(closes, window=10, vol_threshold_pct=25.0)
        high_vol_count = sum(1 for lbl in labels if lbl == REGIME_HIGH_VOL)
        assert high_vol_count > 0


class TestLabelRegimesEdgeCases:
    def test_empty_input(self) -> None:
        assert label_regimes([]) == []

    def test_single_bar(self) -> None:
        labels = label_regimes([100.0])
        assert labels == [None]

    def test_input_shorter_than_window(self) -> None:
        labels = label_regimes([100.0, 110.0], window=5)
        assert all(lbl is None for lbl in labels)

    def test_window_equals_length(self) -> None:
        labels = label_regimes([100.0] * 10, window=10)
        assert all(lbl is None for lbl in labels)

    def test_window_one_returns_all_none(self) -> None:
        labels = label_regimes([100.0] * 10, window=1)
        assert all(lbl is None for lbl in labels)

    def test_zero_prices_handled(self) -> None:
        closes = [0.0] * 50
        labels = label_regimes(closes, window=10)
        assert len(labels) == 50
        for lbl in labels:
            assert lbl is None or lbl in VALID_REGIMES


class TestLabelRegimesThresholds:
    def test_high_trend_threshold_suppresses_trend(self) -> None:
        closes = _make_uptrend(100, step=0.1)
        labels = label_regimes(closes, window=20, trend_threshold=10.0)
        trend_count = sum(1 for lbl in labels if lbl == REGIME_TREND)
        assert trend_count == 0

    def test_low_trend_threshold_increases_trend(self) -> None:
        closes = _make_uptrend(100, step=1.0)
        labels_low = label_regimes(closes, window=20, trend_threshold=0.001)
        labels_high = label_regimes(closes, window=20, trend_threshold=0.5)
        trend_low = sum(1 for lbl in labels_low if lbl == REGIME_TREND)
        trend_high = sum(1 for lbl in labels_high if lbl == REGIME_TREND)
        assert trend_low >= trend_high

    def test_vol_threshold_100_suppresses_high_vol(self) -> None:
        closes = _make_volatile(100, swing=30.0)
        labels = label_regimes(closes, window=10, vol_threshold_pct=100.0)
        hv = sum(1 for lbl in labels if lbl == REGIME_HIGH_VOL)
        assert hv == 0

    def test_window_size_affects_labels(self) -> None:
        closes = _make_uptrend(200, step=0.5)
        labels_short = label_regimes(closes, window=5)
        labels_long = label_regimes(closes, window=50)
        none_short = sum(1 for lbl in labels_short if lbl is None)
        none_long = sum(1 for lbl in labels_long if lbl is None)
        assert none_long > none_short
