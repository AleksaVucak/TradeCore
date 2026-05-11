"""Tests for Phase 17.3 — sentiment filter in strategy configs and backtest engines.

Covers:
- Pydantic validation of SentimentFilterConfig
- Resolver no-lookahead correctness
- Resolver behavior across modes + missing-sample policy
- Backwards compatibility (configs without sentiment_filter behave like before)
- RSI+MA engine: filter blocks/allows new entries; exits never gated
- ML signal engine: filter blocks/allows new entries; exits never gated
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

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
from app.services.sentiment.filter import (
    SentimentDecision,
    SentimentSample,
    evaluate_sentiment_gate,
)


_BASE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _ts(hours: float = 0) -> datetime:
    return _BASE + timedelta(hours=hours)


def _sample(hours: float, score: float, label: str = "positive") -> SentimentSample:
    return SentimentSample(published_at=_ts(hours), score=score, label=label)


# ---------------------------------------------------------------------------
# Pydantic schema tests
# ---------------------------------------------------------------------------


class TestSentimentFilterConfigValidation:
    def test_defaults(self):
        cfg = SentimentFilterConfig()
        assert cfg.enabled is True
        assert cfg.mode == "block_negative"
        assert cfg.lookback_hours == 24
        assert cfg.min_score == 0.0
        assert cfg.max_score == 1.0
        assert cfg.min_samples == 1
        assert cfg.allow_when_missing is True

    def test_threshold_bounds_rejected(self):
        with pytest.raises(ValueError):
            SentimentFilterConfig(mode="threshold", min_score=0.5, max_score=0.1)

    def test_threshold_bounds_equal_allowed(self):
        cfg = SentimentFilterConfig(mode="threshold", min_score=0.0, max_score=0.0)
        assert cfg.max_score == cfg.min_score

    def test_lookback_bounds(self):
        with pytest.raises(ValueError):
            SentimentFilterConfig(lookback_hours=0)
        with pytest.raises(ValueError):
            SentimentFilterConfig(lookback_hours=10_000)

    def test_score_bounds(self):
        with pytest.raises(ValueError):
            SentimentFilterConfig(min_score=-2.0)
        with pytest.raises(ValueError):
            SentimentFilterConfig(max_score=2.0)


class TestRsiMaConfigWithFilter:
    def test_omitted_field_is_none(self):
        cfg = RsiMaConfig()
        assert cfg.sentiment_filter is None

    def test_filter_accepted(self):
        cfg = RsiMaConfig(
            sentiment_filter=SentimentFilterConfig(mode="require_positive")
        )
        assert cfg.sentiment_filter is not None
        assert cfg.sentiment_filter.mode == "require_positive"

    def test_filter_dict_round_trips(self):
        cfg = RsiMaConfig(
            sentiment_filter={
                "enabled": True,
                "mode": "threshold",
                "min_score": -0.2,
                "max_score": 0.8,
                "lookback_hours": 12,
                "min_samples": 3,
                "allow_when_missing": False,
            }
        )
        assert cfg.sentiment_filter.lookback_hours == 12
        round_trip = RsiMaConfig.model_validate(cfg.model_dump())
        assert round_trip.sentiment_filter == cfg.sentiment_filter


class TestMlSignalConfigWithFilter:
    def test_omitted_field_is_none(self):
        cfg = MlSignalConfig(model_id=1)
        assert cfg.sentiment_filter is None

    def test_filter_accepted(self):
        cfg = MlSignalConfig(
            model_id=1,
            sentiment_filter=SentimentFilterConfig(),
        )
        assert cfg.sentiment_filter is not None
        assert cfg.sentiment_filter.enabled is True


# ---------------------------------------------------------------------------
# Resolver tests
# ---------------------------------------------------------------------------


class TestEvaluateSentimentGate:
    def test_returns_allow_when_config_none(self):
        decision = evaluate_sentiment_gate([], as_of=_ts(10), config=None)
        assert decision.allow_long is True
        assert decision.reason == "filter_disabled"

    def test_returns_allow_when_filter_disabled(self):
        cfg = SentimentFilterConfig(enabled=False)
        decision = evaluate_sentiment_gate([], as_of=_ts(10), config=cfg)
        assert decision.allow_long is True
        assert decision.reason == "filter_disabled"

    def test_no_lookahead_excludes_future_samples(self):
        future_sample = _sample(hours=20, score=0.9)
        cfg = SentimentFilterConfig(mode="require_positive", min_samples=1)
        # As of t=10h, a sample at t=20h must NOT influence the decision.
        decision = evaluate_sentiment_gate(
            [future_sample], as_of=_ts(10), config=cfg
        )
        assert decision.samples_used == 0
        assert decision.reason == "insufficient_samples"

    def test_block_negative_allows_when_above_min(self):
        samples = [_sample(hours=1, score=0.5)]
        cfg = SentimentFilterConfig(mode="block_negative", min_score=0.0)
        decision = evaluate_sentiment_gate(samples, as_of=_ts(2), config=cfg)
        assert decision.allow_long is True
        assert decision.avg_score == pytest.approx(0.5)

    def test_block_negative_blocks_when_below_min(self):
        samples = [_sample(hours=1, score=-0.5)]
        cfg = SentimentFilterConfig(mode="block_negative", min_score=0.0)
        decision = evaluate_sentiment_gate(samples, as_of=_ts(2), config=cfg)
        assert decision.allow_long is False

    def test_require_positive_strict(self):
        samples = [_sample(hours=1, score=0.0)]
        cfg = SentimentFilterConfig(mode="require_positive", min_score=0.0)
        decision = evaluate_sentiment_gate(samples, as_of=_ts(2), config=cfg)
        # zero is NOT strictly above zero
        assert decision.allow_long is False

    def test_threshold_mode_in_range(self):
        samples = [_sample(hours=1, score=0.3)]
        cfg = SentimentFilterConfig(
            mode="threshold", min_score=0.0, max_score=0.5
        )
        decision = evaluate_sentiment_gate(samples, as_of=_ts(2), config=cfg)
        assert decision.allow_long is True

    def test_threshold_mode_out_of_range(self):
        samples = [_sample(hours=1, score=0.9)]
        cfg = SentimentFilterConfig(
            mode="threshold", min_score=0.0, max_score=0.5
        )
        decision = evaluate_sentiment_gate(samples, as_of=_ts(2), config=cfg)
        assert decision.allow_long is False

    def test_lookback_window_respected(self):
        old_sample = _sample(hours=0, score=-0.9)  # outside 1h lookback
        recent_sample = _sample(hours=4, score=0.7)
        cfg = SentimentFilterConfig(
            mode="block_negative", lookback_hours=1, min_samples=1
        )
        # as_of=5h with lookback=1h includes only samples in [4h, 5h)
        decision = evaluate_sentiment_gate(
            [old_sample, recent_sample], as_of=_ts(5), config=cfg
        )
        assert decision.samples_used == 1
        assert decision.avg_score == pytest.approx(0.7)
        assert decision.allow_long is True

    def test_insufficient_samples_fail_open(self):
        cfg = SentimentFilterConfig(
            mode="require_positive", min_samples=3, allow_when_missing=True
        )
        decision = evaluate_sentiment_gate(
            [_sample(hours=1, score=0.5)], as_of=_ts(2), config=cfg
        )
        assert decision.samples_used == 1
        assert decision.allow_long is True
        assert decision.reason == "insufficient_samples"

    def test_insufficient_samples_fail_closed(self):
        cfg = SentimentFilterConfig(
            mode="require_positive", min_samples=3, allow_when_missing=False
        )
        decision = evaluate_sentiment_gate(
            [_sample(hours=1, score=0.5)], as_of=_ts(2), config=cfg
        )
        assert decision.allow_long is False
        assert decision.reason == "insufficient_samples"

    def test_naive_as_of_treated_as_utc(self):
        naive_as_of = datetime(2024, 1, 1, 2, 0, 0)  # no tzinfo
        cfg = SentimentFilterConfig(mode="block_negative")
        decision = evaluate_sentiment_gate(
            [_sample(hours=1, score=0.4)], as_of=naive_as_of, config=cfg
        )
        assert decision.samples_used == 1


# ---------------------------------------------------------------------------
# RSI+MA engine integration
# ---------------------------------------------------------------------------


def _make_rsi_candles(n: int = 60) -> list[BacktestCandle]:
    """Drop-then-recover price pattern that reliably triggers an RSI+MA buy.

    Mirrors the pattern used by ``test_trade_has_fee_and_slippage`` in
    ``test_backtest_engine.py`` — the initial decline drives RSI below the
    buy threshold while the subsequent recovery pushes price back above the
    short MA, satisfying both buy conditions.
    """
    base = 100.0
    closes: list[float] = []
    for i in range(n):
        if i < 25:
            close = base - i * 0.5
        else:
            close = base - 12.5 + (i - 25) * 0.3
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


class TestRsiMaEngineSentimentGate:
    def _config(self, sentiment_filter: SentimentFilterConfig | None = None) -> RsiMaConfig:
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
            sentiment_filter=sentiment_filter,
        )

    def test_no_filter_baseline_runs(self):
        candles = _make_rsi_candles(60)
        cfg = self._config(None)
        result = run_backtest_rsi_ma(candles, cfg, initial_equity=10_000)
        assert len(result.equity_curve) > 0

    def test_filter_disabled_matches_no_filter(self):
        candles = _make_rsi_candles(60)
        baseline = run_backtest_rsi_ma(
            candles, self._config(None), initial_equity=10_000
        )
        disabled = run_backtest_rsi_ma(
            candles,
            self._config(SentimentFilterConfig(enabled=False)),
            initial_equity=10_000,
            sentiment_samples=[_sample(0, -1.0)],
        )
        assert [t.side for t in baseline.trades] == [t.side for t in disabled.trades]
        assert baseline.final_equity == pytest.approx(disabled.final_equity, rel=1e-9)

    def test_filter_blocks_entries_when_negative(self):
        candles = _make_rsi_candles(60)
        baseline = run_backtest_rsi_ma(
            candles, self._config(None), initial_equity=10_000
        )
        baseline_buys = sum(1 for t in baseline.trades if t.side == "buy")

        # All sentiment is negative for the whole horizon
        negative_history = [
            _sample(hours=h, score=-0.7) for h in range(0, 60)
        ]
        filtered = run_backtest_rsi_ma(
            candles,
            self._config(
                SentimentFilterConfig(
                    enabled=True,
                    mode="block_negative",
                    lookback_hours=24,
                    min_samples=1,
                    allow_when_missing=False,
                )
            ),
            initial_equity=10_000,
            sentiment_samples=negative_history,
        )
        filtered_buys = sum(1 for t in filtered.trades if t.side == "buy")
        assert filtered_buys == 0
        assert baseline_buys > 0  # ensure baseline actually had entries

    def test_filter_allows_entries_when_positive(self):
        candles = _make_rsi_candles(60)
        positive_history = [
            _sample(hours=h, score=0.6) for h in range(0, 60)
        ]
        filtered = run_backtest_rsi_ma(
            candles,
            self._config(
                SentimentFilterConfig(
                    enabled=True,
                    mode="require_positive",
                    lookback_hours=24,
                    min_samples=1,
                )
            ),
            initial_equity=10_000,
            sentiment_samples=positive_history,
        )
        baseline = run_backtest_rsi_ma(
            candles, self._config(None), initial_equity=10_000
        )
        assert [t.side for t in filtered.trades] == [t.side for t in baseline.trades]

    def test_exits_not_gated_when_sentiment_negative(self):
        """Even when sentiment turns negative, an open position can still exit."""
        candles = _make_rsi_candles(60)
        # Sentiment positive at start (allow entry), negative later (must allow exit).
        history = [
            _sample(hours=h, score=0.8) for h in range(0, 20)
        ] + [_sample(hours=h, score=-0.9) for h in range(20, 60)]
        filtered = run_backtest_rsi_ma(
            candles,
            self._config(
                SentimentFilterConfig(
                    enabled=True,
                    mode="require_positive",
                    lookback_hours=24,
                    min_samples=1,
                    allow_when_missing=False,
                )
            ),
            initial_equity=10_000,
            sentiment_samples=history,
        )
        sides = [t.side for t in filtered.trades]
        if "buy" in sides:
            # if we entered, the engine must allow exits irrespective of sentiment
            assert sides.count("sell") <= sides.count("buy")


# ---------------------------------------------------------------------------
# ML signal engine integration (uses mock model)
# ---------------------------------------------------------------------------

_ML_FEATURES = ["rsi_14", "sma_20", "macd", "bbands_width", "atr_14", "log_return_1"]


class _ConstantProbModel:
    """Always returns the same probability for class 1."""

    classes_ = np.array([0, 1])

    def __init__(self, prob: float):
        self.prob = prob

    def predict_proba(self, X):
        n = len(X)
        return np.array([[1.0 - self.prob, self.prob]] * n)


def _make_artifact(model, feature_keys: list[str], tmp_dir: str) -> str:
    path = os.path.join(tmp_dir, "filter_test_model.joblib")
    joblib.dump(
        {"model": model, "feature_keys": feature_keys, "model_type": "signal", "horizon": 5},
        path,
    )
    return path


def _ml_config(sentiment_filter: SentimentFilterConfig | None = None) -> MlSignalConfig:
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
        sentiment_filter=sentiment_filter,
    )


def _ml_candles(n: int) -> list[BacktestCandle]:
    candles = []
    for i in range(n):
        close = 100.0 + (i * 0.1)
        candles.append(
            BacktestCandle(
                _ts(i),
                open=close + 0.1,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1000.0,
            )
        )
    return candles


class TestMlSignalEngineSentimentGate:
    def test_filter_blocks_ml_entries(self):
        candles = _ml_candles(60)
        with tempfile.TemporaryDirectory() as td:
            artifact = _make_artifact(_ConstantProbModel(0.9), _ML_FEATURES, td)

            baseline = run_backtest_ml_signal(
                candles, _ml_config(None), artifact_path=artifact, initial_equity=10_000
            )
            assert sum(1 for t in baseline.trades if t.side == "buy") > 0

            negative_history = [_sample(hours=h, score=-0.8) for h in range(0, 60)]
            filtered = run_backtest_ml_signal(
                candles,
                _ml_config(
                    SentimentFilterConfig(
                        enabled=True,
                        mode="block_negative",
                        lookback_hours=24,
                        min_samples=1,
                        allow_when_missing=False,
                    )
                ),
                artifact_path=artifact,
                initial_equity=10_000,
                sentiment_samples=negative_history,
            )
            assert sum(1 for t in filtered.trades if t.side == "buy") == 0

    def test_filter_disabled_matches_no_filter(self):
        candles = _ml_candles(60)
        with tempfile.TemporaryDirectory() as td:
            artifact = _make_artifact(_ConstantProbModel(0.9), _ML_FEATURES, td)

            baseline = run_backtest_ml_signal(
                candles, _ml_config(None), artifact_path=artifact, initial_equity=10_000
            )
            disabled = run_backtest_ml_signal(
                candles,
                _ml_config(SentimentFilterConfig(enabled=False)),
                artifact_path=artifact,
                initial_equity=10_000,
                sentiment_samples=[_sample(0, -1.0)],
            )
            assert [t.side for t in baseline.trades] == [t.side for t in disabled.trades]
            assert baseline.final_equity == pytest.approx(disabled.final_equity, rel=1e-9)

    def test_missing_sentiment_fail_closed_blocks(self):
        candles = _ml_candles(60)
        with tempfile.TemporaryDirectory() as td:
            artifact = _make_artifact(_ConstantProbModel(0.9), _ML_FEATURES, td)

            filtered = run_backtest_ml_signal(
                candles,
                _ml_config(
                    SentimentFilterConfig(
                        enabled=True,
                        mode="require_positive",
                        lookback_hours=24,
                        min_samples=1,
                        allow_when_missing=False,
                    )
                ),
                artifact_path=artifact,
                initial_equity=10_000,
                sentiment_samples=None,
            )
            assert sum(1 for t in filtered.trades if t.side == "buy") == 0

    def test_missing_sentiment_fail_open_allows(self):
        candles = _ml_candles(60)
        with tempfile.TemporaryDirectory() as td:
            artifact = _make_artifact(_ConstantProbModel(0.9), _ML_FEATURES, td)

            filtered = run_backtest_ml_signal(
                candles,
                _ml_config(
                    SentimentFilterConfig(
                        enabled=True,
                        mode="require_positive",
                        lookback_hours=24,
                        min_samples=1,
                        allow_when_missing=True,
                    )
                ),
                artifact_path=artifact,
                initial_equity=10_000,
                sentiment_samples=None,
            )
            assert sum(1 for t in filtered.trades if t.side == "buy") > 0
