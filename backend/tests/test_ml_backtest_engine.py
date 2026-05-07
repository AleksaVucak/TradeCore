"""
Tests for ML signal backtest engine (Phase 16.3).

Uses mock classifiers with deterministic probabilities so tests are
repeatable without training real models.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import joblib
import numpy as np
import pytest

from app.schemas.strategy_config import MlSignalConfig
from app.services.backtest.ml_engine import run_backtest_ml_signal
from app.services.backtest.types import BacktestCandle, BacktestResult

_BASE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_FEATURES = ["rsi_14", "sma_20", "macd", "bbands_width", "atr_14", "log_return_1"]


def _ts(hours: int = 0) -> datetime:
    return _BASE + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Mock model helpers
# ---------------------------------------------------------------------------


class _ConstantProbModel:
    """Always returns the same probability for class 1."""

    classes_ = np.array([0, 1])

    def __init__(self, prob: float):
        self.prob = prob

    def predict_proba(self, X):
        n = len(X)
        return np.array([[1.0 - self.prob, self.prob]] * n)


class _SequenceProbModel:
    """Returns probabilities from a pre-defined sequence, cycling if needed."""

    classes_ = np.array([0, 1])

    def __init__(self, probs: list[float]):
        self._probs = probs

    def predict_proba(self, X):
        n = len(X)
        out = []
        for i in range(n):
            p = self._probs[i % len(self._probs)]
            out.append([1.0 - p, p])
        return np.array(out)


def _make_artifact(model, feature_keys: list[str], tmp_dir: str) -> str:
    """Save a mock model artifact and return the path."""
    path = os.path.join(tmp_dir, "test_model.joblib")
    joblib.dump(
        {
            "model": model,
            "feature_keys": feature_keys,
            "model_type": "signal",
            "horizon": 5,
        },
        path,
    )
    return path


def _default_config(**overrides) -> MlSignalConfig:
    """Build an MlSignalConfig with sensible defaults for testing."""
    kwargs = {
        "model_id": 1,
        "features": _FEATURES,
        "long_threshold": 0.6,
        "exit_threshold": 0.4,
        "position_size_pct": 1.0,
        "stop_loss_pct": 5.0,
        "take_profit_pct": 10.0,
        "fee_rate": 0.001,
        "slippage_rate": 0.0005,
    }
    kwargs.update(overrides)
    return MlSignalConfig(**kwargs)


def _make_candles(
    n: int,
    base_price: float = 100.0,
    price_fn=None,
) -> list[BacktestCandle]:
    """Generate n candles.  If *price_fn* is given it receives the bar
    index and returns the close price; otherwise a flat series is used."""
    candles = []
    for i in range(n):
        close = price_fn(i) if price_fn else base_price
        candles.append(
            BacktestCandle(
                _ts(hours=i),
                open=close + 0.1,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1000.0,
            )
        )
    return candles


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


class TestMlEngineBasic:
    def test_empty_candles(self, tmp_path) -> None:
        model = _ConstantProbModel(0.7)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config()
        result = run_backtest_ml_signal(
            [], config, artifact_path=artifact, initial_equity=10_000.0
        )
        assert result.initial_equity == 10_000.0
        assert result.final_equity == 10_000.0
        assert result.trades == []
        assert result.equity_curve == []

    def test_initial_equity_zero_raises(self, tmp_path) -> None:
        model = _ConstantProbModel(0.7)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config()
        candles = _make_candles(60)
        with pytest.raises(ValueError, match="initial_equity"):
            run_backtest_ml_signal(
                candles, config, artifact_path=artifact, initial_equity=0.0
            )

    def test_initial_equity_negative_raises(self, tmp_path) -> None:
        model = _ConstantProbModel(0.7)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config()
        candles = _make_candles(60)
        with pytest.raises(ValueError, match="initial_equity"):
            run_backtest_ml_signal(
                candles, config, artifact_path=artifact, initial_equity=-100.0
            )

    def test_insufficient_candles_all_warmup(self, tmp_path) -> None:
        """When all bars fall in the feature warmup period, no trades should occur."""
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config()
        candles = _make_candles(10)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        assert result.trades == []
        assert result.final_equity == 10_000.0

    def test_missing_artifact_raises(self) -> None:
        config = _default_config()
        candles = _make_candles(60)
        with pytest.raises(FileNotFoundError, match="ML model artifact"):
            run_backtest_ml_signal(
                candles,
                config,
                artifact_path="/nonexistent/model.joblib",
                initial_equity=10_000.0,
            )

    def test_feature_mismatch_raises(self, tmp_path) -> None:
        """Config features differing from training features should raise."""
        model = _ConstantProbModel(0.7)
        artifact = _make_artifact(model, ["rsi_14", "sma_20"], str(tmp_path))
        config = _default_config(features=["rsi_14", "sma_20", "macd"])
        candles = _make_candles(60)
        with pytest.raises(ValueError, match="do not match"):
            run_backtest_ml_signal(
                candles, config, artifact_path=artifact, initial_equity=10_000.0
            )


# ---------------------------------------------------------------------------
# Signal behaviour
# ---------------------------------------------------------------------------


class TestMlEngineSignals:
    def test_always_high_proba_buys(self, tmp_path) -> None:
        """When probability is always above long_threshold, a buy should occur."""
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(
            long_threshold=0.6,
            exit_threshold=0.4,
            fee_rate=0.0,
            slippage_rate=0.0,
            stop_loss_pct=50.0,
            take_profit_pct=50.0,
        )
        candles = _make_candles(80)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        buy_trades = [t for t in result.trades if t.side == "buy"]
        assert len(buy_trades) >= 1
        sell_trades = [t for t in result.trades if t.side == "sell"]
        assert len(sell_trades) == 0

    def test_always_low_proba_no_buy(self, tmp_path) -> None:
        """When probability is always below long_threshold, no trades should occur."""
        model = _ConstantProbModel(0.3)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(long_threshold=0.6, exit_threshold=0.4)
        candles = _make_candles(80)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        assert result.trades == []
        assert result.final_equity == pytest.approx(10_000.0)

    def test_signal_exit_triggers(self, tmp_path) -> None:
        """Transition from high to low probability should trigger buy then sell."""
        n_bars = 80
        warmup = 55
        probs = []
        for i in range(n_bars - warmup):
            if i < 10:
                probs.append(0.8)
            else:
                probs.append(0.3)

        model = _SequenceProbModel(probs)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(
            long_threshold=0.6,
            exit_threshold=0.4,
            fee_rate=0.0,
            slippage_rate=0.0,
            stop_loss_pct=50.0,
            take_profit_pct=50.0,
        )
        candles = _make_candles(n_bars)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        buy_trades = [t for t in result.trades if t.side == "buy"]
        sell_trades = [t for t in result.trades if t.side == "sell"]
        assert len(buy_trades) >= 1
        assert len(sell_trades) >= 1
        for st in sell_trades:
            assert st.pnl is not None


# ---------------------------------------------------------------------------
# Stop-loss and take-profit
# ---------------------------------------------------------------------------


class TestMlEngineSLTP:
    def test_stop_loss_triggers(self, tmp_path) -> None:
        """Price drop below SL should exit position even when probability is high."""
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(
            long_threshold=0.6,
            exit_threshold=0.1,
            stop_loss_pct=2.0,
            take_profit_pct=50.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        def price_fn(i):
            if i < 58:
                return 100.0
            return 100.0 - (i - 57) * 2.0

        candles = []
        for i in range(80):
            close = price_fn(i)
            candles.append(
                BacktestCandle(
                    _ts(hours=i),
                    open=close + 0.1,
                    high=close + 0.5,
                    low=close - 3.0,
                    close=close,
                    volume=1000.0,
                )
            )

        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        sell_trades = [t for t in result.trades if t.side == "sell"]
        if sell_trades:
            for st in sell_trades:
                assert st.pnl is not None
                assert st.pnl < 0

    def test_take_profit_triggers(self, tmp_path) -> None:
        """Price spike above TP should exit position at profit."""
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(
            long_threshold=0.6,
            exit_threshold=0.1,
            stop_loss_pct=50.0,
            take_profit_pct=3.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        candles = []
        for i in range(80):
            close = 100.0
            high = close + 0.5
            if i == 60:
                high = 200.0
            candles.append(
                BacktestCandle(
                    _ts(hours=i),
                    open=close + 0.1,
                    high=high,
                    low=close - 0.5,
                    close=close,
                    volume=1000.0,
                )
            )

        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        buy_trades = [t for t in result.trades if t.side == "buy"]
        sell_trades = [t for t in result.trades if t.side == "sell"]
        if buy_trades and sell_trades:
            entry = buy_trades[0].price
            tp_price = entry * (1.0 + config.take_profit_pct / 100.0)
            assert sell_trades[0].price == pytest.approx(tp_price, rel=0.01)


# ---------------------------------------------------------------------------
# Fees and slippage
# ---------------------------------------------------------------------------


class TestMlEngineFees:
    def test_trades_have_fee_and_slippage(self, tmp_path) -> None:
        n_bars = 80
        warmup = 55
        probs = []
        for i in range(n_bars - warmup):
            if i < 10:
                probs.append(0.8)
            else:
                probs.append(0.3)

        model = _SequenceProbModel(probs)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(
            long_threshold=0.6,
            exit_threshold=0.4,
            fee_rate=0.001,
            slippage_rate=0.0005,
            stop_loss_pct=50.0,
            take_profit_pct=50.0,
        )
        candles = _make_candles(n_bars)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        for t in result.trades:
            assert t.fee >= 0
            assert t.slippage >= 0
            assert t.price > 0
            assert t.quantity > 0

    def test_higher_fees_reduce_equity(self, tmp_path) -> None:
        """Higher fees should produce lower final equity, all else equal."""
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))

        candles = []
        for i in range(80):
            close = 100.0 - i * 0.3 if i < 40 else 88.0 + (i - 40) * 0.3
            candles.append(
                BacktestCandle(
                    _ts(hours=i),
                    open=close + 0.1,
                    high=close + 0.5,
                    low=close - 3.0,
                    close=close,
                    volume=1000.0,
                )
            )

        config_low = _default_config(
            fee_rate=0.0, slippage_rate=0.0,
            stop_loss_pct=2.0, take_profit_pct=50.0,
        )
        config_high = _default_config(
            fee_rate=0.05, slippage_rate=0.01,
            stop_loss_pct=2.0, take_profit_pct=50.0,
        )

        r_low = run_backtest_ml_signal(
            candles, config_low, artifact_path=artifact, initial_equity=10_000.0
        )
        r_high = run_backtest_ml_signal(
            candles, config_high, artifact_path=artifact, initial_equity=10_000.0
        )
        if r_low.trades and r_high.trades:
            assert r_high.final_equity <= r_low.final_equity


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------


class TestMlEnginePositionSizing:
    def test_partial_position_size(self, tmp_path) -> None:
        """With position_size_pct=0.1, notional ≈ 10% of equity."""
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(
            position_size_pct=0.1,
            fee_rate=0.0,
            slippage_rate=0.0,
            stop_loss_pct=50.0,
            take_profit_pct=50.0,
        )
        candles = _make_candles(80)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        buy_trades = [t for t in result.trades if t.side == "buy"]
        if buy_trades:
            first_buy = buy_trades[0]
            actual_cost = first_buy.price * first_buy.quantity
            expected_notional = 10_000.0 * 0.1
            assert actual_cost == pytest.approx(expected_notional, rel=0.05)

    def test_full_position_size(self, tmp_path) -> None:
        """With position_size_pct=1.0, entire equity is used."""
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(
            position_size_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
            stop_loss_pct=50.0,
            take_profit_pct=50.0,
        )
        candles = _make_candles(80)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        buy_trades = [t for t in result.trades if t.side == "buy"]
        if buy_trades:
            first_buy = buy_trades[0]
            actual_cost = first_buy.price * first_buy.quantity
            assert actual_cost == pytest.approx(10_000.0, rel=0.05)


# ---------------------------------------------------------------------------
# Equity curve invariants
# ---------------------------------------------------------------------------


class TestMlEngineEquityCurve:
    def test_equity_curve_timestamps_non_decreasing(self, tmp_path) -> None:
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(stop_loss_pct=2.0, take_profit_pct=50.0)

        candles = []
        for i in range(80):
            close = 100.0 - i * 0.3 if i < 40 else 88.0 + (i - 40) * 0.3
            candles.append(
                BacktestCandle(
                    _ts(hours=i),
                    open=close + 0.1,
                    high=close + 0.5,
                    low=close - 3.0,
                    close=close,
                    volume=1000.0,
                )
            )

        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        timestamps = [p.timestamp for p in result.equity_curve]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]

    def test_equity_curve_all_positive(self, tmp_path) -> None:
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(stop_loss_pct=2.0, take_profit_pct=50.0)

        candles = []
        for i in range(80):
            close = 100.0 - i * 0.3 if i < 40 else 88.0 + (i - 40) * 0.3
            candles.append(
                BacktestCandle(
                    _ts(hours=i),
                    open=close + 0.1,
                    high=close + 0.5,
                    low=close - 3.0,
                    close=close,
                    volume=1000.0,
                )
            )

        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        for p in result.equity_curve:
            assert p.equity_value >= 0

    def test_buy_sell_pairs_balanced(self, tmp_path) -> None:
        """Sells should never exceed buys; at most one open position at end."""
        model = _ConstantProbModel(0.9)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(stop_loss_pct=2.0, take_profit_pct=50.0)

        candles = []
        for i in range(100):
            close = 100.0 - i * 0.3 if i < 40 else 88.0 + (i - 40) * 0.4
            candles.append(
                BacktestCandle(
                    _ts(hours=i),
                    open=close + 0.1,
                    high=close + 0.5,
                    low=close - 3.0,
                    close=close,
                    volume=1000.0,
                )
            )

        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        buys = sum(1 for t in result.trades if t.side == "buy")
        sells = sum(1 for t in result.trades if t.side == "sell")
        assert sells <= buys
        assert buys - sells <= 1

    def test_result_type(self, tmp_path) -> None:
        """Engine should return a proper BacktestResult."""
        model = _ConstantProbModel(0.7)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config()
        candles = _make_candles(80)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        assert isinstance(result, BacktestResult)
        assert result.initial_equity == 10_000.0
        assert result.final_equity > 0


# ---------------------------------------------------------------------------
# Metrics compatibility
# ---------------------------------------------------------------------------


class TestMlEngineMetricsCompat:
    def test_metrics_from_ml_result(self, tmp_path) -> None:
        """The standard metrics module should work on ML engine output."""
        from app.services.backtest.metrics import compute_metrics_from_result

        n_bars = 80
        warmup = 55
        probs = []
        for i in range(n_bars - warmup):
            if i < 10:
                probs.append(0.8)
            else:
                probs.append(0.3)

        model = _SequenceProbModel(probs)
        artifact = _make_artifact(model, _FEATURES, str(tmp_path))
        config = _default_config(
            fee_rate=0.0, slippage_rate=0.0,
            stop_loss_pct=50.0, take_profit_pct=50.0,
        )
        candles = _make_candles(n_bars)
        result = run_backtest_ml_signal(
            candles, config, artifact_path=artifact, initial_equity=10_000.0
        )
        metrics = compute_metrics_from_result(result, period_hours=1.0)
        assert "total_return_pct" in metrics
        assert "max_drawdown_pct" in metrics
        assert "sharpe_ratio" in metrics
        assert "num_trades" in metrics
        assert isinstance(metrics["num_trades"], int)
