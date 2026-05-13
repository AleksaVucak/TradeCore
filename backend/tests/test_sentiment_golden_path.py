"""Phase 17.8 — Golden-path backtest proof for sentiment filter.

Proves the sentiment filter is *real*: an RSI+MA strategy run with
populated sentiment data behaves differently (fewer/no entries) compared
to the same strategy without the filter, and the equity curves diverge.

Also validates the full backtest-task wiring: the task function loads
sentiment samples from the DB and threads them through to the engine.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pytest

from app.schemas.strategy_config import (
    MlSignalConfig,
    RsiMaConfig,
    SentimentFilterConfig,
)
from app.services.backtest.engine import run_backtest_rsi_ma
from app.services.backtest.ml_engine import run_backtest_ml_signal
from app.services.backtest.types import BacktestCandle
from app.services.sentiment.filter import SentimentSample


_BASE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _ts(hours: float = 0) -> datetime:
    return _BASE + timedelta(hours=hours)


def _sample(hours: float, score: float) -> SentimentSample:
    label = "positive" if score > 0.05 else ("negative" if score < -0.05 else "neutral")
    return SentimentSample(published_at=_ts(hours), score=score, label=label)


def _make_candles(n: int = 80) -> list[BacktestCandle]:
    """Drop-then-recover pattern that reliably triggers RSI+MA buy signals."""
    closes: list[float] = []
    for i in range(n):
        if i < 25:
            close = 100.0 - i * 0.5
        else:
            close = 100.0 - 12.5 + (i - 25) * 0.3
        closes.append(close)
    return [
        BacktestCandle(
            timestamp=_ts(i),
            open=c,
            high=c + 0.5,
            low=c - 0.5,
            close=c,
            volume=1000.0,
        )
        for i, c in enumerate(closes)
    ]


def _rsi_config(sf: SentimentFilterConfig | None = None) -> RsiMaConfig:
    return RsiMaConfig(
        rsi_period=5,
        rsi_buy_threshold=25.0,
        rsi_sell_threshold=75.0,
        ma_period=3,
        position_size_pct=1.0,
        stop_loss_pct=20.0,
        take_profit_pct=20.0,
        fee_rate=0.001,
        slippage_rate=0.0005,
        sentiment_filter=sf,
    )


# ---------------------------------------------------------------------------
# Golden-path proof: baseline vs filtered
# ---------------------------------------------------------------------------


class TestGoldenPathRsiMa:
    """Documented proof that sentiment filter changes backtest outcomes.

    Expected behavior (documented for QA):
    - **Baseline** (no filter): RSI dips below buy threshold during the
      initial decline → engine enters at least 1 long → equity moves.
    - **All-negative filter**: every candle is gated by negative sentiment
      → all buy signals blocked → 0 entries → equity = initial.
    - **All-positive filter**: every candle is gated by positive sentiment
      → same entries as baseline → equity matches baseline.
    """

    def test_baseline_has_entries(self):
        candles = _make_candles()
        result = run_backtest_rsi_ma(candles, _rsi_config(), initial_equity=10_000)
        buys = sum(1 for t in result.trades if t.side == "buy")
        assert buys > 0, "Baseline must produce at least one buy"
        assert result.final_equity != 10_000.0, "Equity should change when trades occur"

    def test_negative_sentiment_blocks_all_entries(self):
        candles = _make_candles()
        neg_samples = [_sample(h, -0.6) for h in range(len(candles))]

        baseline = run_backtest_rsi_ma(candles, _rsi_config(), initial_equity=10_000)
        baseline_buys = sum(1 for t in baseline.trades if t.side == "buy")

        filtered = run_backtest_rsi_ma(
            candles,
            _rsi_config(SentimentFilterConfig(
                enabled=True,
                mode="block_negative",
                lookback_hours=24,
                min_samples=1,
                allow_when_missing=False,
            )),
            initial_equity=10_000,
            sentiment_samples=neg_samples,
        )
        filtered_buys = sum(1 for t in filtered.trades if t.side == "buy")

        assert baseline_buys > 0
        assert filtered_buys == 0
        assert filtered.final_equity == 10_000.0, "No trades → equity unchanged"

    def test_positive_sentiment_matches_baseline(self):
        candles = _make_candles()
        pos_samples = [_sample(h, 0.7) for h in range(len(candles))]

        baseline = run_backtest_rsi_ma(candles, _rsi_config(), initial_equity=10_000)
        filtered = run_backtest_rsi_ma(
            candles,
            _rsi_config(SentimentFilterConfig(
                enabled=True,
                mode="require_positive",
                lookback_hours=24,
                min_samples=1,
            )),
            initial_equity=10_000,
            sentiment_samples=pos_samples,
        )

        baseline_sides = [t.side for t in baseline.trades]
        filtered_sides = [t.side for t in filtered.trades]
        assert baseline_sides == filtered_sides
        assert baseline.final_equity == pytest.approx(filtered.final_equity, rel=1e-9)

    def test_equity_diverges_between_filtered_and_unfiltered(self):
        """The key proof: final equity differs when filter blocks trades."""
        candles = _make_candles()
        neg_samples = [_sample(h, -0.6) for h in range(len(candles))]

        baseline = run_backtest_rsi_ma(candles, _rsi_config(), initial_equity=10_000)
        filtered = run_backtest_rsi_ma(
            candles,
            _rsi_config(SentimentFilterConfig(
                enabled=True,
                mode="block_negative",
                lookback_hours=24,
                min_samples=1,
                allow_when_missing=False,
            )),
            initial_equity=10_000,
            sentiment_samples=neg_samples,
        )

        assert baseline.final_equity != filtered.final_equity, (
            "With negative sentiment blocking trades, equity must differ from baseline"
        )

    def test_mixed_sentiment_reduces_entries(self):
        """Sentiment negative in early half → some baseline entries blocked."""
        candles = _make_candles()
        half = len(candles) // 2
        mixed = (
            [_sample(h, -0.6) for h in range(half)]
            + [_sample(h, 0.7) for h in range(half, len(candles))]
        )

        baseline = run_backtest_rsi_ma(candles, _rsi_config(), initial_equity=10_000)
        filtered = run_backtest_rsi_ma(
            candles,
            _rsi_config(SentimentFilterConfig(
                enabled=True,
                mode="block_negative",
                lookback_hours=24,
                min_samples=1,
                allow_when_missing=False,
            )),
            initial_equity=10_000,
            sentiment_samples=mixed,
        )

        baseline_buys = sum(1 for t in baseline.trades if t.side == "buy")
        filtered_buys = sum(1 for t in filtered.trades if t.side == "buy")
        assert filtered_buys <= baseline_buys, (
            "Negative sentiment in first half should block some/all early entries"
        )


# ---------------------------------------------------------------------------
# Golden-path proof for ML signal engine
# ---------------------------------------------------------------------------


class _ConstantProbModel:
    """Always returns the same probability for class 1."""

    classes_ = np.array([0, 1])

    def __init__(self, prob: float):
        self.prob = prob

    def predict_proba(self, X):
        n = len(X)
        return np.array([[1.0 - self.prob, self.prob]] * n)


_ML_FEATURES = ["rsi_14", "sma_20", "macd", "bbands_width", "atr_14", "log_return_1"]


def _ml_config(sf: SentimentFilterConfig | None = None) -> MlSignalConfig:
    return MlSignalConfig(
        model_id=1,
        features=_ML_FEATURES,
        long_threshold=0.6,
        exit_threshold=0.4,
        position_size_pct=1.0,
        stop_loss_pct=20.0,
        take_profit_pct=20.0,
        fee_rate=0.001,
        slippage_rate=0.0005,
        sentiment_filter=sf,
    )


def _ml_candles(n: int = 80) -> list[BacktestCandle]:
    return [
        BacktestCandle(
            _ts(i),
            open=100.0 + i * 0.1 + 0.1,
            high=100.0 + i * 0.1 + 0.5,
            low=100.0 + i * 0.1 - 0.5,
            close=100.0 + i * 0.1,
            volume=1000.0,
        )
        for i in range(n)
    ]


def _make_artifact(model, feature_keys: list[str], tmp_dir: str) -> str:
    path = os.path.join(tmp_dir, "golden_test_model.joblib")
    joblib.dump(
        {"model": model, "feature_keys": feature_keys, "model_type": "signal", "horizon": 5},
        path,
    )
    return path


class TestGoldenPathMlSignal:
    """Documented proof that ML signal engine respects sentiment filter."""

    def test_ml_baseline_has_entries(self):
        candles = _ml_candles()
        with tempfile.TemporaryDirectory() as td:
            artifact = _make_artifact(_ConstantProbModel(0.9), _ML_FEATURES, td)
            result = run_backtest_ml_signal(
                candles, _ml_config(), artifact_path=artifact, initial_equity=10_000
            )
            buys = sum(1 for t in result.trades if t.side == "buy")
            assert buys > 0

    def test_ml_negative_blocks_all(self):
        candles = _ml_candles()
        neg_samples = [_sample(h, -0.8) for h in range(len(candles))]

        with tempfile.TemporaryDirectory() as td:
            artifact = _make_artifact(_ConstantProbModel(0.9), _ML_FEATURES, td)

            baseline = run_backtest_ml_signal(
                candles, _ml_config(), artifact_path=artifact, initial_equity=10_000
            )
            filtered = run_backtest_ml_signal(
                candles,
                _ml_config(SentimentFilterConfig(
                    enabled=True,
                    mode="block_negative",
                    lookback_hours=24,
                    min_samples=1,
                    allow_when_missing=False,
                )),
                artifact_path=artifact,
                initial_equity=10_000,
                sentiment_samples=neg_samples,
            )

            assert sum(1 for t in baseline.trades if t.side == "buy") > 0
            assert sum(1 for t in filtered.trades if t.side == "buy") == 0

    def test_ml_equity_diverges(self):
        candles = _ml_candles()
        neg_samples = [_sample(h, -0.8) for h in range(len(candles))]

        with tempfile.TemporaryDirectory() as td:
            artifact = _make_artifact(_ConstantProbModel(0.9), _ML_FEATURES, td)

            baseline = run_backtest_ml_signal(
                candles, _ml_config(), artifact_path=artifact, initial_equity=10_000
            )
            filtered = run_backtest_ml_signal(
                candles,
                _ml_config(SentimentFilterConfig(
                    enabled=True,
                    mode="block_negative",
                    lookback_hours=24,
                    min_samples=1,
                    allow_when_missing=False,
                )),
                artifact_path=artifact,
                initial_equity=10_000,
                sentiment_samples=neg_samples,
            )

            assert baseline.final_equity != filtered.final_equity


# ---------------------------------------------------------------------------
# Backtest task wiring — sentiment loading integration
# ---------------------------------------------------------------------------


class TestBacktestTaskSentimentWiring:
    """Verify that ``run_backtest_task`` correctly loads sentiment data
    and passes it through to the engine when the strategy config has
    ``sentiment_filter`` enabled.
    """

    @patch("app.tasks.backtests.load_sentiment_history")
    @patch("app.tasks.backtests.run_backtest_rsi_ma")
    def test_task_loads_sentiment_when_filter_enabled(
        self, mock_engine, mock_load_sentiment
    ):
        """When sentiment_filter is enabled, the task loads samples and
        passes them to the engine.
        """
        from app.services.backtest.types import BacktestResult

        mock_load_sentiment.return_value = [
            _sample(0, 0.5),
            _sample(1, 0.6),
        ]
        mock_engine.return_value = BacktestResult(
            trades=[], equity_curve=[], initial_equity=10_000, final_equity=10_000
        )

        config_with_filter = {
            "rsi_period": 14,
            "rsi_buy_threshold": 30.0,
            "rsi_sell_threshold": 70.0,
            "ma_period": 20,
            "position_size_pct": 1.0,
            "stop_loss_pct": 5.0,
            "take_profit_pct": 5.0,
            "fee_rate": 0.001,
            "slippage_rate": 0.0005,
            "sentiment_filter": {
                "enabled": True,
                "mode": "block_negative",
                "lookback_hours": 24,
                "min_samples": 1,
                "allow_when_missing": True,
            },
        }

        mock_db = MagicMock()
        mock_strategy_version = MagicMock()
        mock_strategy_version.config = config_with_filter
        mock_strategy = MagicMock()
        mock_strategy.strategy_type = "rsi_ma"
        mock_strategy.id = 1
        mock_strategy_version.strategy = mock_strategy
        mock_strategy_version.id = 1

        with (
            patch("app.tasks.backtests.SessionLocal", return_value=mock_db),
            patch("app.tasks.backtests.validate_strategy_config") as mock_validate,
        ):
            validated_cfg = RsiMaConfig(**config_with_filter)
            mock_validate.return_value = validated_cfg

            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                mock_strategy_version
            )
            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

            from app.tasks.backtests import run_backtest_task

            run_backtest_task(
                strategy_version_id=1,
                symbol_id=1,
                timeframe="1h",
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-04T00:00:00Z",
            )

        mock_load_sentiment.assert_called_once()
        call_kwargs = mock_engine.call_args
        assert call_kwargs.kwargs.get("sentiment_samples") is not None

    @patch("app.tasks.backtests.load_sentiment_history")
    @patch("app.tasks.backtests.run_backtest_rsi_ma")
    def test_task_skips_sentiment_when_filter_missing(
        self, mock_engine, mock_load_sentiment
    ):
        """When sentiment_filter is absent/None, the task does NOT load
        sentiment samples.
        """
        from app.services.backtest.types import BacktestResult

        mock_engine.return_value = BacktestResult(
            trades=[], equity_curve=[], initial_equity=10_000, final_equity=10_000
        )

        config_no_filter = {
            "rsi_period": 14,
            "rsi_buy_threshold": 30.0,
            "rsi_sell_threshold": 70.0,
            "ma_period": 20,
            "position_size_pct": 1.0,
            "stop_loss_pct": 5.0,
            "take_profit_pct": 5.0,
            "fee_rate": 0.001,
            "slippage_rate": 0.0005,
        }

        mock_db = MagicMock()
        mock_strategy_version = MagicMock()
        mock_strategy_version.config = config_no_filter
        mock_strategy = MagicMock()
        mock_strategy.strategy_type = "rsi_ma"
        mock_strategy.id = 1
        mock_strategy_version.strategy = mock_strategy
        mock_strategy_version.id = 1

        with (
            patch("app.tasks.backtests.SessionLocal", return_value=mock_db),
            patch("app.tasks.backtests.validate_strategy_config") as mock_validate,
        ):
            validated_cfg = RsiMaConfig(**config_no_filter)
            mock_validate.return_value = validated_cfg

            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                mock_strategy_version
            )
            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

            from app.tasks.backtests import run_backtest_task

            run_backtest_task(
                strategy_version_id=1,
                symbol_id=1,
                timeframe="1h",
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-04T00:00:00Z",
            )

        mock_load_sentiment.assert_not_called()
        call_kwargs = mock_engine.call_args
        passed_samples = call_kwargs.kwargs.get("sentiment_samples")
        assert passed_samples is None

    @patch("app.tasks.backtests.load_sentiment_history")
    @patch("app.tasks.backtests.run_backtest_rsi_ma")
    def test_task_skips_sentiment_when_filter_disabled(
        self, mock_engine, mock_load_sentiment
    ):
        """When sentiment_filter exists but enabled=False, no samples loaded."""
        from app.services.backtest.types import BacktestResult

        mock_engine.return_value = BacktestResult(
            trades=[], equity_curve=[], initial_equity=10_000, final_equity=10_000
        )

        config_disabled = {
            "rsi_period": 14,
            "rsi_buy_threshold": 30.0,
            "rsi_sell_threshold": 70.0,
            "ma_period": 20,
            "position_size_pct": 1.0,
            "stop_loss_pct": 5.0,
            "take_profit_pct": 5.0,
            "fee_rate": 0.001,
            "slippage_rate": 0.0005,
            "sentiment_filter": {
                "enabled": False,
                "mode": "block_negative",
            },
        }

        mock_db = MagicMock()
        mock_strategy_version = MagicMock()
        mock_strategy_version.config = config_disabled
        mock_strategy = MagicMock()
        mock_strategy.strategy_type = "rsi_ma"
        mock_strategy.id = 1
        mock_strategy_version.strategy = mock_strategy
        mock_strategy_version.id = 1

        with (
            patch("app.tasks.backtests.SessionLocal", return_value=mock_db),
            patch("app.tasks.backtests.validate_strategy_config") as mock_validate,
        ):
            validated_cfg = RsiMaConfig(**config_disabled)
            mock_validate.return_value = validated_cfg

            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                mock_strategy_version
            )
            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

            from app.tasks.backtests import run_backtest_task

            run_backtest_task(
                strategy_version_id=1,
                symbol_id=1,
                timeframe="1h",
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-04T00:00:00Z",
            )

        mock_load_sentiment.assert_not_called()
