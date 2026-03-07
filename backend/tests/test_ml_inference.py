"""Tests for ML regime inference service (Phase 9.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.ml.inference import (
    get_latest_model,
    label_candles,
    predict_regimes,
)


def _make_candle(i: int, base: float = 100.0) -> SimpleNamespace:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
    price = base + i * 0.5
    return SimpleNamespace(
        id=i,
        symbol_id=1,
        timeframe="1h",
        timestamp=ts,
        open=price,
        high=price + 2.0,
        low=price - 2.0,
        close=price + 1.0,
        volume=1000.0 + i * 10,
    )


def _make_candles(n: int = 100) -> list[SimpleNamespace]:
    return [_make_candle(i) for i in range(n)]


class TestPredictRegimes:
    @pytest.fixture(autouse=True)
    def _patch_load(self, tmp_path):
        mock_clf = MagicMock()
        mock_clf.predict.return_value = ["trend", "range", "high_vol"] * 50

        self._patcher = patch(
            "app.services.ml.inference.load_model",
            return_value=(mock_clf, [
                "log_return", "rolling_return_20", "volatility_20", "atr_14",
                "momentum_10", "rsi_14", "sma_20", "volume_ratio_20", "bb_width_20",
            ]),
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    def test_returns_correct_length(self) -> None:
        candles = _make_candles(50)
        preds = predict_regimes(
            opens=[c.open for c in candles],
            highs=[c.high for c in candles],
            lows=[c.low for c in candles],
            closes=[c.close for c in candles],
            volumes=[c.volume for c in candles],
            artifact_path="/fake/model.joblib",
        )
        assert len(preds) == 50

    def test_early_bars_are_none(self) -> None:
        candles = _make_candles(50)
        preds = predict_regimes(
            opens=[c.open for c in candles],
            highs=[c.high for c in candles],
            lows=[c.low for c in candles],
            closes=[c.close for c in candles],
            volumes=[c.volume for c in candles],
            artifact_path="/fake/model.joblib",
        )
        assert preds[0] is None

    def test_later_bars_have_predictions(self) -> None:
        candles = _make_candles(50)
        preds = predict_regimes(
            opens=[c.open for c in candles],
            highs=[c.high for c in candles],
            lows=[c.low for c in candles],
            closes=[c.close for c in candles],
            volumes=[c.volume for c in candles],
            artifact_path="/fake/model.joblib",
        )
        non_none = [p for p in preds if p is not None]
        assert len(non_none) > 0
        for p in non_none:
            assert p in {"trend", "range", "high_vol"}

    def test_empty_input(self) -> None:
        preds = predict_regimes(
            opens=[], highs=[], lows=[], closes=[], volumes=[],
            artifact_path="/fake/model.joblib",
        )
        assert preds == []


class TestGetLatestModel:
    def test_returns_latest(self) -> None:
        model_a = SimpleNamespace(id=1, created_at=datetime(2026, 1, 1))
        model_b = SimpleNamespace(id=2, created_at=datetime(2026, 2, 1))

        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        filter_mock = MagicMock()
        query_mock.filter.return_value = filter_mock
        order_mock = MagicMock()
        filter_mock.order_by.return_value = order_mock
        order_mock.first.return_value = model_b

        result = get_latest_model(db, symbol_id=1, timeframe="1h")
        assert result.id == 2

    def test_returns_none_when_no_models(self) -> None:
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        filter_mock = MagicMock()
        query_mock.filter.return_value = filter_mock
        order_mock = MagicMock()
        filter_mock.order_by.return_value = order_mock
        order_mock.first.return_value = None

        result = get_latest_model(db, symbol_id=1, timeframe="1h")
        assert result is None


class TestLabelCandles:
    @pytest.fixture(autouse=True)
    def _patch_deps(self, tmp_path):
        mock_clf = MagicMock()
        mock_clf.predict.return_value = ["trend", "range", "high_vol"] * 50

        self._load_patcher = patch(
            "app.services.ml.inference.load_model",
            return_value=(mock_clf, [
                "log_return", "rolling_return_20", "volatility_20", "atr_14",
                "momentum_10", "rsi_14", "sma_20", "volume_ratio_20", "bb_width_20",
            ]),
        )
        self._load_patcher.start()
        yield
        self._load_patcher.stop()

    def _mock_db(self, n_candles: int = 100) -> MagicMock:
        candles = _make_candles(n_candles)
        meta = SimpleNamespace(
            id=1,
            artifact_path="/fake/model.joblib",
            symbol_id=1,
            timeframe="1h",
        )

        db = MagicMock()

        query_results = {}
        call_count = {"n": 0}

        def query_side_effect(model):
            call_count["n"] += 1
            mock = MagicMock()
            model_name = getattr(model, "__name__", str(model))

            if model_name == "MLModelMetadata":
                filter_mock = MagicMock()
                mock.filter.return_value = filter_mock
                order_mock = MagicMock()
                filter_mock.order_by.return_value = order_mock
                order_mock.first.return_value = meta
            elif model_name == "Candle":
                filter_mock = MagicMock()
                mock.filter.return_value = filter_mock
                filter_mock.filter.return_value = filter_mock
                filter_mock.order_by.return_value = filter_mock
                filter_mock.all.return_value = candles
            return mock

        db.query.side_effect = query_side_effect

        execute_mock = MagicMock()
        db.execute.return_value = execute_mock

        return db

    def test_returns_summary(self) -> None:
        db = self._mock_db()
        result = label_candles(db, symbol_id=1, timeframe="1h")
        assert "model_id" in result
        assert "labeled_bars" in result
        assert "total_candles" in result
        assert "regime_distribution" in result
        assert result["model_id"] == 1

    def test_labeled_bars_positive(self) -> None:
        db = self._mock_db()
        result = label_candles(db, symbol_id=1, timeframe="1h")
        assert result["labeled_bars"] > 0

    def test_regime_distribution_populated(self) -> None:
        db = self._mock_db()
        result = label_candles(db, symbol_id=1, timeframe="1h")
        dist = result["regime_distribution"]
        assert isinstance(dist, dict)
        total = sum(dist.values())
        assert total == result["labeled_bars"]

    def test_add_all_called(self) -> None:
        db = self._mock_db()
        label_candles(db, symbol_id=1, timeframe="1h")
        db.add_all.assert_called_once()
        db.commit.assert_called_once()

    def test_delete_called_for_idempotency(self) -> None:
        db = self._mock_db()
        label_candles(db, symbol_id=1, timeframe="1h")
        db.execute.assert_called_once()

    def test_too_few_candles_raises(self) -> None:
        db = self._mock_db(n_candles=10)
        with pytest.raises(ValueError, match="Not enough candles"):
            label_candles(db, symbol_id=1, timeframe="1h")

    def test_no_model_raises(self) -> None:
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        filter_mock = MagicMock()
        query_mock.filter.return_value = filter_mock
        order_mock = MagicMock()
        filter_mock.order_by.return_value = order_mock
        order_mock.first.return_value = None

        with pytest.raises(ValueError, match="No trained model found"):
            label_candles(db, symbol_id=1, timeframe="1h")

    def test_skipped_bars_accounts_for_warmup(self) -> None:
        db = self._mock_db()
        result = label_candles(db, symbol_id=1, timeframe="1h")
        assert result["skipped_bars"] == result["total_candles"] - result["labeled_bars"]
        assert result["skipped_bars"] >= 0
