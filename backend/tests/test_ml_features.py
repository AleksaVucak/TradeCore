"""Tests for ML feature engineering module (Phase 9.1)."""

import math

import pytest

from app.services.ml.features import (
    atr,
    bollinger_band_width,
    compute_feature_matrix,
    log_returns,
    momentum,
    rolling_returns,
    rolling_volatility,
    rolling_volume_ratio,
    true_range,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approx(val: float | None, expected: float, rel: float = 1e-4) -> bool:
    if val is None:
        return False
    return abs(val - expected) <= rel * max(abs(expected), 1e-9) + 1e-9


# ---------------------------------------------------------------------------
# log_returns
# ---------------------------------------------------------------------------

class TestLogReturns:
    def test_basic(self) -> None:
        closes = [100.0, 110.0, 105.0]
        lr = log_returns(closes)
        assert lr[0] is None
        assert _approx(lr[1], math.log(110 / 100))
        assert _approx(lr[2], math.log(105 / 110))

    def test_empty(self) -> None:
        assert log_returns([]) == []

    def test_single(self) -> None:
        lr = log_returns([100.0])
        assert lr == [None]

    def test_zero_price_handled(self) -> None:
        lr = log_returns([0.0, 100.0])
        assert lr[0] is None
        assert lr[1] == 0.0


# ---------------------------------------------------------------------------
# rolling_returns
# ---------------------------------------------------------------------------

class TestRollingReturns:
    def test_basic(self) -> None:
        closes = [100.0, 105.0, 110.0, 115.0, 120.0]
        rr = rolling_returns(closes, 3)
        assert rr[0] is None
        assert rr[1] is None
        assert rr[2] is None
        assert _approx(rr[3], math.log(115 / 100))
        assert _approx(rr[4], math.log(120 / 105))

    def test_period_zero(self) -> None:
        rr = rolling_returns([100.0, 110.0], 0)
        assert all(v is None for v in rr)

    def test_empty(self) -> None:
        assert rolling_returns([], 5) == []


# ---------------------------------------------------------------------------
# rolling_volatility
# ---------------------------------------------------------------------------

class TestRollingVolatility:
    def test_constant_prices_zero_vol(self) -> None:
        closes = [100.0] * 10
        rv = rolling_volatility(closes, 5)
        for i in range(5, 10):
            assert rv[i] is not None
            assert rv[i] == pytest.approx(0.0, abs=1e-10)

    def test_nones_before_period(self) -> None:
        closes = [100.0, 110.0, 105.0, 115.0, 120.0]
        rv = rolling_volatility(closes, 3)
        assert rv[0] is None
        assert rv[1] is None
        assert rv[2] is None

    def test_positive_for_varying_prices(self) -> None:
        closes = [100.0, 110.0, 95.0, 105.0, 90.0, 115.0]
        rv = rolling_volatility(closes, 3)
        for i in range(3, 6):
            assert rv[i] is not None
            assert rv[i] > 0

    def test_too_short(self) -> None:
        rv = rolling_volatility([100.0, 110.0], 5)
        assert all(v is None for v in rv)


# ---------------------------------------------------------------------------
# true_range
# ---------------------------------------------------------------------------

class TestTrueRange:
    def test_basic(self) -> None:
        highs = [105.0, 110.0, 108.0]
        lows = [95.0, 100.0, 99.0]
        closes = [100.0, 105.0, 102.0]
        tr = true_range(highs, lows, closes)
        assert tr[0] is None
        assert tr[1] == max(110 - 100, abs(110 - 100), abs(100 - 100))
        assert tr[2] == max(108 - 99, abs(108 - 105), abs(99 - 105))

    def test_empty(self) -> None:
        assert true_range([], [], []) == []


# ---------------------------------------------------------------------------
# atr
# ---------------------------------------------------------------------------

class TestATR:
    def test_nones_before_period(self) -> None:
        n = 20
        highs = [float(105 + i) for i in range(n)]
        lows = [float(95 + i) for i in range(n)]
        closes = [float(100 + i) for i in range(n)]
        result = atr(highs, lows, closes, period=14)
        for i in range(14):
            assert result[i] is None
        assert result[14] is not None
        assert result[14] > 0

    def test_positive_values(self) -> None:
        n = 30
        highs = [float(105 + i % 5) for i in range(n)]
        lows = [float(95 + i % 5) for i in range(n)]
        closes = [float(100 + i % 5) for i in range(n)]
        result = atr(highs, lows, closes, period=5)
        for i in range(6, n):
            assert result[i] is not None
            assert result[i] > 0

    def test_too_short(self) -> None:
        result = atr([105.0], [95.0], [100.0], period=14)
        assert all(v is None for v in result)


# ---------------------------------------------------------------------------
# momentum
# ---------------------------------------------------------------------------

class TestMomentum:
    def test_basic(self) -> None:
        closes = [100.0, 105.0, 110.0, 120.0, 130.0]
        m = momentum(closes, 2)
        assert m[0] is None
        assert m[1] is None
        assert _approx(m[2], (110 - 100) / 100 * 100)
        assert _approx(m[3], (120 - 105) / 105 * 100)
        assert _approx(m[4], (130 - 110) / 110 * 100)

    def test_negative_momentum(self) -> None:
        closes = [100.0, 90.0, 80.0]
        m = momentum(closes, 1)
        assert m[1] is not None
        assert m[1] < 0
        assert m[2] is not None
        assert m[2] < 0

    def test_empty(self) -> None:
        assert momentum([], 5) == []


# ---------------------------------------------------------------------------
# rolling_volume_ratio
# ---------------------------------------------------------------------------

class TestRollingVolumeRatio:
    def test_constant_volume(self) -> None:
        volumes = [1000.0] * 10
        vr = rolling_volume_ratio(volumes, 5)
        for i in range(4, 10):
            assert vr[i] is not None
            assert vr[i] == pytest.approx(1.0, rel=1e-6)

    def test_nones_before_period(self) -> None:
        volumes = [100.0, 200.0, 300.0]
        vr = rolling_volume_ratio(volumes, 5)
        assert all(v is None for v in vr)

    def test_spike_above_one(self) -> None:
        volumes = [100.0] * 5 + [500.0]
        vr = rolling_volume_ratio(volumes, 5)
        assert vr[5] is not None
        assert vr[5] > 1.0


# ---------------------------------------------------------------------------
# bollinger_band_width
# ---------------------------------------------------------------------------

class TestBollingerBandWidth:
    def test_constant_prices_zero_width(self) -> None:
        closes = [100.0] * 25
        bb = bollinger_band_width(closes, period=20)
        for i in range(19, 25):
            assert bb[i] is not None
            assert bb[i] == pytest.approx(0.0, abs=1e-10)

    def test_positive_for_varying_prices(self) -> None:
        closes = [100.0 + (i % 3) * 5.0 for i in range(30)]
        bb = bollinger_band_width(closes, period=10)
        for i in range(10, 30):
            assert bb[i] is not None
            assert bb[i] > 0

    def test_nones_before_period(self) -> None:
        bb = bollinger_band_width([100.0, 110.0], period=5)
        assert all(v is None for v in bb)


# ---------------------------------------------------------------------------
# compute_feature_matrix
# ---------------------------------------------------------------------------

class TestComputeFeatureMatrix:
    def _make_ohlcv(self, n: int = 50):
        opens = [100.0 + i * 0.5 for i in range(n)]
        highs = [o + 2.0 for o in opens]
        lows = [o - 2.0 for o in opens]
        closes = [o + 1.0 for o in opens]
        volumes = [1000.0 + i * 10 for i in range(n)]
        return opens, highs, lows, closes, volumes

    def test_returns_correct_length(self) -> None:
        opens, highs, lows, closes, volumes = self._make_ohlcv(50)
        rows = compute_feature_matrix(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
        )
        assert len(rows) == 50

    def test_all_keys_present(self) -> None:
        opens, highs, lows, closes, volumes = self._make_ohlcv(50)
        rows = compute_feature_matrix(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
        )
        expected_keys = {
            "log_return",
            "rolling_return_20",
            "volatility_20",
            "atr_14",
            "momentum_10",
            "rsi_14",
            "sma_20",
            "volume_ratio_20",
            "bb_width_20",
        }
        for row in rows:
            assert set(row.keys()) == expected_keys

    def test_late_bars_have_values(self) -> None:
        opens, highs, lows, closes, volumes = self._make_ohlcv(50)
        rows = compute_feature_matrix(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
        )
        last = rows[-1]
        for key, val in last.items():
            assert val is not None, f"{key} should not be None at end of series"

    def test_early_bars_have_nones(self) -> None:
        opens, highs, lows, closes, volumes = self._make_ohlcv(50)
        rows = compute_feature_matrix(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
        )
        first = rows[0]
        none_count = sum(1 for v in first.values() if v is None)
        assert none_count > 0

    def test_empty_input(self) -> None:
        rows = compute_feature_matrix(
            opens=[], highs=[], lows=[], closes=[], volumes=[]
        )
        assert rows == []

    def test_custom_periods(self) -> None:
        opens, highs, lows, closes, volumes = self._make_ohlcv(50)
        rows = compute_feature_matrix(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            rsi_period=7,
            ma_period=10,
            atr_period=7,
            vol_period=10,
            momentum_period=5,
            volume_ratio_period=10,
            bb_period=10,
        )
        assert len(rows) == 50
        assert "rsi_7" in rows[0]
        assert "sma_10" in rows[0]
        assert "atr_7" in rows[0]
        assert "volatility_10" in rows[0]
        assert "momentum_5" in rows[0]
        assert "volume_ratio_10" in rows[0]
        assert "bb_width_10" in rows[0]
