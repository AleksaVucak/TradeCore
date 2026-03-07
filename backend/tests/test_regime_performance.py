"""Tests for per-regime performance analysis (Phase 9.5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.ml.regime_performance import (
    _match_trade_to_regime,
    compute_regime_performance,
)


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ts(hours: int) -> datetime:
    return BASE + timedelta(hours=hours)


def _make_regime_labels(regime_sequence: list[str]) -> list[SimpleNamespace]:
    """Create mock RegimeLabel objects from a sequence of regime strings."""
    return [
        SimpleNamespace(
            id=i,
            model_id=1,
            symbol_id=1,
            timeframe="1h",
            timestamp=_ts(i),
            regime=regime_sequence[i],
        )
        for i in range(len(regime_sequence))
    ]


def _make_trades(
    entries: list[tuple[int, float]],
) -> list[SimpleNamespace]:
    """Create mock Trade objects: entries is [(hour_offset, pnl), ...]."""
    return [
        SimpleNamespace(
            id=f"trade-{i}",
            backtest_run_id="run-1",
            timestamp=_ts(hour),
            side="sell",
            price=100.0,
            quantity=1.0,
            fee=0.0,
            slippage=0.0,
            pnl=pnl,
        )
        for i, (hour, pnl) in enumerate(entries)
    ]


def _mock_db(
    labels: list[SimpleNamespace],
    trades: list[SimpleNamespace],
) -> MagicMock:
    db = MagicMock()

    from app.models.regime_label import RegimeLabel
    from app.models.trade import Trade

    def query_side_effect(model):
        mock = MagicMock()
        if model is RegimeLabel:
            filter_mock = MagicMock()
            mock.filter.return_value = filter_mock
            filter_mock.all.return_value = labels
        elif model is Trade:
            filter_mock = MagicMock()
            mock.filter.return_value = filter_mock
            order_mock = MagicMock()
            filter_mock.order_by.return_value = order_mock
            order_mock.all.return_value = trades
        return mock

    db.query.side_effect = query_side_effect
    return db


class TestMatchTradeToRegime:
    def test_exact_match(self) -> None:
        regime_map = {_ts(0): "trend", _ts(1): "range"}
        assert _match_trade_to_regime(_ts(0), regime_map, 3600) == "trend"

    def test_nearest_within_tolerance(self) -> None:
        regime_map = {_ts(0): "trend", _ts(2): "range"}
        trade_ts = _ts(0) + timedelta(minutes=30)
        result = _match_trade_to_regime(trade_ts, regime_map, 3600)
        assert result == "trend"

    def test_outside_tolerance_returns_none(self) -> None:
        regime_map = {_ts(0): "trend"}
        trade_ts = _ts(0) + timedelta(hours=2)
        result = _match_trade_to_regime(trade_ts, regime_map, 3600)
        assert result is None

    def test_empty_map_returns_none(self) -> None:
        result = _match_trade_to_regime(_ts(0), {}, 3600)
        assert result is None

    def test_picks_closest_when_two_within_tolerance(self) -> None:
        regime_map = {_ts(0): "trend", _ts(1): "range"}
        trade_ts = _ts(0) + timedelta(minutes=50)
        result = _match_trade_to_regime(trade_ts, regime_map, 3600)
        assert result == "range"


class TestComputeRegimePerformance:
    def test_basic_structure(self) -> None:
        regimes_seq = ["trend"] * 10 + ["range"] * 10 + ["high_vol"] * 10
        labels = _make_regime_labels(regimes_seq)
        trades = _make_trades([(2, 50.0), (5, -20.0), (12, 30.0), (22, -10.0)])
        db = _mock_db(labels, trades)

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(29),
            model_id=1,
        )

        assert result["run_id"] == "run-1"
        assert result["total_bars"] == 30
        assert "regimes" in result
        assert len(result["regimes"]) == 3

    def test_regime_names_and_labels(self) -> None:
        labels = _make_regime_labels(["trend", "range", "high_vol"])
        db = _mock_db(labels, [])

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(2),
            model_id=1,
        )

        regime_keys = [r["regime"] for r in result["regimes"]]
        assert regime_keys == ["trend", "range", "high_vol"]

        regime_labels = [r["label"] for r in result["regimes"]]
        assert regime_labels == ["Trend", "Range", "High Volatility"]

    def test_trades_matched_to_correct_regime(self) -> None:
        regimes_seq = ["trend"] * 5 + ["range"] * 5
        labels = _make_regime_labels(regimes_seq)
        trades = _make_trades([(1, 100.0), (3, -50.0), (6, 75.0)])
        db = _mock_db(labels, trades)

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(9),
            model_id=1,
        )

        trend_item = next(r for r in result["regimes"] if r["regime"] == "trend")
        range_item = next(r for r in result["regimes"] if r["regime"] == "range")

        assert trend_item["num_trades"] == 2
        assert range_item["num_trades"] == 1

    def test_pnl_aggregation(self) -> None:
        regimes_seq = ["trend"] * 10
        labels = _make_regime_labels(regimes_seq)
        trades = _make_trades([(1, 100.0), (3, -50.0), (5, 200.0)])
        db = _mock_db(labels, trades)

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(9),
            model_id=1,
        )

        trend_item = next(r for r in result["regimes"] if r["regime"] == "trend")
        assert trend_item["total_pnl"] == 250.0
        assert trend_item["avg_pnl"] == pytest.approx(83.33, abs=0.01)
        assert trend_item["wins"] == 2
        assert trend_item["losses"] == 1

    def test_win_rate_calculation(self) -> None:
        regimes_seq = ["range"] * 10
        labels = _make_regime_labels(regimes_seq)
        trades = _make_trades([(1, 10.0), (3, 20.0), (5, -5.0), (7, 15.0)])
        db = _mock_db(labels, trades)

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(9),
            model_id=1,
        )

        range_item = next(r for r in result["regimes"] if r["regime"] == "range")
        assert range_item["win_rate"] == 75.0

    def test_no_trades_yields_zero_metrics(self) -> None:
        labels = _make_regime_labels(["trend"] * 5)
        db = _mock_db(labels, [])

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(4),
            model_id=1,
        )

        trend_item = next(r for r in result["regimes"] if r["regime"] == "trend")
        assert trend_item["num_trades"] == 0
        assert trend_item["total_pnl"] == 0.0
        assert trend_item["avg_pnl"] is None
        assert trend_item["win_rate"] is None

    def test_bars_percentage(self) -> None:
        regimes_seq = ["trend"] * 6 + ["range"] * 3 + ["high_vol"] * 1
        labels = _make_regime_labels(regimes_seq)
        db = _mock_db(labels, [])

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(9),
            model_id=1,
        )

        trend_item = next(r for r in result["regimes"] if r["regime"] == "trend")
        range_item = next(r for r in result["regimes"] if r["regime"] == "range")
        high_vol_item = next(r for r in result["regimes"] if r["regime"] == "high_vol")

        assert trend_item["bars_pct"] == 60.0
        assert range_item["bars_pct"] == 30.0
        assert high_vol_item["bars_pct"] == 10.0

    def test_total_trades_matched(self) -> None:
        regimes_seq = ["trend"] * 5 + ["range"] * 5
        labels = _make_regime_labels(regimes_seq)
        trades = _make_trades([(1, 10.0), (6, 20.0)])
        db = _mock_db(labels, trades)

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(9),
            model_id=1,
        )

        assert result["total_trades_matched"] == 2

    def test_unmatched_trades_not_counted(self) -> None:
        regimes_seq = ["trend"] * 3
        labels = _make_regime_labels(regimes_seq)
        trades = _make_trades([(1, 10.0), (100, 50.0)])
        db = _mock_db(labels, trades)

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(2),
            model_id=1,
        )

        assert result["total_trades_matched"] == 1

    def test_empty_labels_yields_empty_result(self) -> None:
        db = _mock_db([], [])

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(9),
            model_id=1,
        )

        assert result["total_bars"] == 0
        assert result["total_trades_matched"] == 0
        for regime in result["regimes"]:
            assert regime["bars"] == 0
            assert regime["num_trades"] == 0

    def test_zero_pnl_counted_as_win(self) -> None:
        labels = _make_regime_labels(["trend"] * 5)
        trades = _make_trades([(1, 0.0)])
        db = _mock_db(labels, trades)

        result = compute_regime_performance(
            db,
            run_id="run-1",
            symbol_id=1,
            timeframe="1h",
            start_time=_ts(0),
            end_time=_ts(4),
            model_id=1,
        )

        trend_item = next(r for r in result["regimes"] if r["regime"] == "trend")
        assert trend_item["wins"] == 1
        assert trend_item["losses"] == 0
        assert trend_item["win_rate"] == 100.0
