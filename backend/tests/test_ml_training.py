"""Tests for ML training pipeline (Phase 9.2)."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.ml.training import (
    FEATURE_KEYS,
    _build_dataset,
    _fetch_candles,
    load_model,
    train_regime_model,
)


def _make_candle(
    i: int, base: float = 100.0, symbol_id: int = 1, timeframe: str = "1h"
) -> SimpleNamespace:
    """Create a fake Candle-like object with sequential prices."""
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
    price = base + i * 0.5
    return SimpleNamespace(
        id=i,
        symbol_id=symbol_id,
        timeframe=timeframe,
        timestamp=ts,
        open=price,
        high=price + 2.0,
        low=price - 2.0,
        close=price + 1.0,
        volume=1000.0 + i * 10,
    )


def _make_candles(n: int = 200, **kwargs) -> list[SimpleNamespace]:
    return [_make_candle(i, **kwargs) for i in range(n)]


class TestBuildDataset:
    def test_returns_aligned_x_y_ts(self) -> None:
        candles = _make_candles(100)
        X, y, ts = _build_dataset(candles, label_window=10)
        assert len(X) == len(y) == len(ts)
        assert len(X) > 0

    def test_no_nones_in_X(self) -> None:
        candles = _make_candles(100)
        X, y, _ = _build_dataset(candles, label_window=10)
        for row in X:
            for val in row:
                assert val is not None

    def test_feature_count_matches(self) -> None:
        candles = _make_candles(100)
        X, _, _ = _build_dataset(candles, label_window=10)
        for row in X:
            assert len(row) == len(FEATURE_KEYS)

    def test_labels_are_valid(self) -> None:
        candles = _make_candles(100)
        _, y, _ = _build_dataset(candles, label_window=10)
        valid = {"trend", "range", "high_vol"}
        for lbl in y:
            assert lbl in valid

    def test_too_few_candles(self) -> None:
        candles = _make_candles(5)
        X, y, ts = _build_dataset(candles, label_window=10)
        assert len(X) == 0

    def test_timestamps_are_datetimes(self) -> None:
        candles = _make_candles(100)
        _, _, ts = _build_dataset(candles, label_window=10)
        for t in ts:
            assert isinstance(t, datetime)


class TestTrainRegimeModel:
    @pytest.fixture(autouse=True)
    def _setup_tmpdir(self, tmp_path):
        self._artifact_dir = str(tmp_path)
        self._patcher = patch(
            "app.services.ml.training.ARTIFACT_DIR", tmp_path
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    def _mock_db(self, n_candles: int = 200) -> MagicMock:
        candles = _make_candles(n_candles)
        db = MagicMock()

        query_mock = MagicMock()
        db.query.return_value = query_mock
        filter_mock = MagicMock()
        query_mock.filter.return_value = filter_mock
        filter_mock.filter.return_value = filter_mock
        filter_mock.order_by.return_value = filter_mock
        filter_mock.all.return_value = candles

        meta_holder = {}

        def add_side_effect(obj):
            meta_holder["meta"] = obj
            obj.id = 1

        db.add.side_effect = add_side_effect

        def refresh_side_effect(obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = 1

        db.refresh.side_effect = refresh_side_effect

        return db

    def test_returns_expected_keys(self) -> None:
        db = self._mock_db()
        result = train_regime_model(db, symbol_id=1)
        assert "model_id" in result
        assert "artifact_path" in result
        assert "accuracy" in result
        assert "classification_report" in result
        assert "n_train" in result
        assert "n_test" in result
        assert "label_distribution" in result

    def test_creates_artifact_file(self) -> None:
        db = self._mock_db()
        result = train_regime_model(db, symbol_id=1)
        assert os.path.isfile(result["artifact_path"])

    def test_accuracy_between_0_and_1(self) -> None:
        db = self._mock_db()
        result = train_regime_model(db, symbol_id=1)
        assert 0.0 <= result["accuracy"] <= 1.0

    def test_db_add_and_commit_called(self) -> None:
        db = self._mock_db()
        train_regime_model(db, symbol_id=1)
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_too_few_candles_raises(self) -> None:
        db = self._mock_db(n_candles=20)
        with pytest.raises(ValueError, match="Not enough candles"):
            train_regime_model(db, symbol_id=1)

    def test_model_name_in_artifact_path(self) -> None:
        db = self._mock_db()
        result = train_regime_model(db, symbol_id=1, model_name="test_model")
        assert "test_model" in result["artifact_path"]

    def test_label_distribution_populated(self) -> None:
        db = self._mock_db()
        result = train_regime_model(db, symbol_id=1)
        dist = result["label_distribution"]
        assert isinstance(dist, dict)
        assert sum(dist.values()) > 0


class TestLoadModel:
    def test_roundtrip(self, tmp_path) -> None:
        with patch("app.services.ml.training.ARTIFACT_DIR", tmp_path):
            db = MagicMock()
            candles = _make_candles(200)

            query_mock = MagicMock()
            db.query.return_value = query_mock
            filter_mock = MagicMock()
            query_mock.filter.return_value = filter_mock
            filter_mock.filter.return_value = filter_mock
            filter_mock.order_by.return_value = filter_mock
            filter_mock.all.return_value = candles

            def add_side_effect(obj):
                obj.id = 1

            db.add.side_effect = add_side_effect
            db.refresh.side_effect = lambda obj: None

            result = train_regime_model(db, symbol_id=1)
            clf, keys = load_model(result["artifact_path"])

            assert keys == FEATURE_KEYS
            assert hasattr(clf, "predict")

    def test_loaded_model_can_predict(self, tmp_path) -> None:
        with patch("app.services.ml.training.ARTIFACT_DIR", tmp_path):
            db = MagicMock()
            candles = _make_candles(200)

            query_mock = MagicMock()
            db.query.return_value = query_mock
            filter_mock = MagicMock()
            query_mock.filter.return_value = filter_mock
            filter_mock.filter.return_value = filter_mock
            filter_mock.order_by.return_value = filter_mock
            filter_mock.all.return_value = candles

            db.add.side_effect = lambda obj: setattr(obj, "id", 1)
            db.refresh.side_effect = lambda obj: None

            result = train_regime_model(db, symbol_id=1)
            clf, keys = load_model(result["artifact_path"])

            sample = [[0.01] * len(keys)]
            preds = clf.predict(sample)
            assert len(preds) == 1
            assert preds[0] in {"trend", "range", "high_vol"}
