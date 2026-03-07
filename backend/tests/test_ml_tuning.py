"""Tests for ML model fine-tuning / hyperparameter search (Phase 9.6)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.ml.training import (
    DEFAULT_PARAM_GRID,
    FEATURE_KEYS,
    train_regime_model,
)


def _make_candle(
    i: int, base: float = 100.0, symbol_id: int = 1, timeframe: str = "1h"
) -> SimpleNamespace:
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


def _mock_db(n_candles: int = 200) -> MagicMock:
    candles = _make_candles(n_candles)
    db = MagicMock()

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

    def refresh_side_effect(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = 1

    db.refresh.side_effect = refresh_side_effect

    return db


class TestTuningMode:
    @pytest.fixture(autouse=True)
    def _setup_tmpdir(self, tmp_path):
        self._artifact_dir = str(tmp_path)
        self._patcher = patch(
            "app.services.ml.training.ARTIFACT_DIR", tmp_path
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    def test_tune_returns_tuning_keys(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=True,
            tune_n_iter=3,
            tune_cv=2,
        )
        assert result["tuned"] is True
        assert "best_params" in result
        assert "cv_best_score" in result
        assert "cv_folds" in result
        assert result["cv_folds"] == 2
        assert result["n_iter"] == 3

    def test_tune_best_params_are_dict(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=True,
            tune_n_iter=3,
            tune_cv=2,
        )
        assert isinstance(result["best_params"], dict)
        assert len(result["best_params"]) > 0

    def test_tune_cv_score_in_valid_range(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=True,
            tune_n_iter=3,
            tune_cv=2,
        )
        assert 0.0 <= result["cv_best_score"] <= 1.0

    def test_tune_accuracy_between_0_and_1(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=True,
            tune_n_iter=3,
            tune_cv=2,
        )
        assert 0.0 <= result["accuracy"] <= 1.0

    def test_tune_creates_artifact(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=True,
            tune_n_iter=3,
            tune_cv=2,
        )
        assert os.path.isfile(result["artifact_path"])
        assert "_tuned_" in result["artifact_path"]

    def test_tune_stores_metadata_in_db(self) -> None:
        db = _mock_db()
        train_regime_model(
            db,
            symbol_id=1,
            tune=True,
            tune_n_iter=3,
            tune_cv=2,
        )
        db.add.assert_called_once()
        db.commit.assert_called_once()

        meta = db.add.call_args[0][0]
        assert meta.metrics["tuned"] is True
        assert "best_params" in meta.metrics
        assert "cv_best_score" in meta.metrics

    def test_tune_custom_param_grid(self) -> None:
        db = _mock_db()
        custom_grid = {
            "n_estimators": [50, 100],
            "max_depth": [5, 10],
        }
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=True,
            tune_n_iter=2,
            tune_cv=2,
            tune_param_grid=custom_grid,
        )
        assert result["tuned"] is True
        params = result["best_params"]
        assert params["n_estimators"] in [50, 100]
        assert params["max_depth"] in [5, 10]


class TestNoTuneMode:
    @pytest.fixture(autouse=True)
    def _setup_tmpdir(self, tmp_path):
        self._patcher = patch(
            "app.services.ml.training.ARTIFACT_DIR", tmp_path
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    def test_no_tune_returns_tuned_false(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=False,
        )
        assert result.get("tuned") is False

    def test_no_tune_has_best_params(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=False,
            n_estimators=200,
            max_depth=12,
        )
        assert result["best_params"] == {
            "n_estimators": 200,
            "max_depth": 12,
        }

    def test_no_tune_no_cv_keys(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=False,
        )
        assert "cv_best_score" not in result
        assert "cv_folds" not in result

    def test_no_tune_artifact_no_tuned_suffix(self) -> None:
        db = _mock_db()
        result = train_regime_model(
            db,
            symbol_id=1,
            tune=False,
        )
        assert "_tuned_" not in result["artifact_path"]


class TestDefaultParamGrid:
    def test_grid_has_expected_keys(self) -> None:
        expected = {"n_estimators", "max_depth", "min_samples_split",
                    "min_samples_leaf", "max_features"}
        assert set(DEFAULT_PARAM_GRID.keys()) == expected

    def test_grid_values_are_lists(self) -> None:
        for key, values in DEFAULT_PARAM_GRID.items():
            assert isinstance(values, list), f"{key} should be a list"
            assert len(values) >= 2, f"{key} should have at least 2 options"
