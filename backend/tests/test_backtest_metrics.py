"""
Tests for backtest metrics module (Phase 6.2 / Phase 11.1).
"""

import math
from datetime import datetime, timezone, timedelta

import pytest

from app.services.backtest import (
    BacktestCandle,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
    compute_metrics,
    compute_metrics_from_result,
    run_backtest_rsi_ma,
)
from app.schemas.strategy_config import RsiMaConfig


_BASE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _ts(hours: int = 0) -> datetime:
    return _BASE + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Basic / edge cases
# ---------------------------------------------------------------------------

class TestMetricsBasic:
    def test_empty_equity_uses_initial_final(self) -> None:
        m = compute_metrics([], [], initial_equity=10_000.0)
        assert m["final_equity"] == 10_000.0
        assert m["total_return"] == 0.0
        assert m["total_return_pct"] == 0.0
        assert m["max_drawdown"] == 0.0
        assert m["num_trades"] == 0
        assert m["win_rate"] == 0.0
        assert m["sharpe_ratio"] == 0.0

    def test_zero_initial_equity(self) -> None:
        m = compute_metrics(
            [],
            [EquityPoint(_ts(0), 100.0)],
            initial_equity=0.0,
        )
        assert m["total_return"] == 0.0
        assert m["final_equity"] == 0.0
        assert m["num_trades"] == 0

    def test_single_equity_point(self) -> None:
        curve = [EquityPoint(_ts(0), 11_000.0)]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["total_return"] == 1_000.0
        assert m["total_return_pct"] == 10.0
        assert m["max_drawdown"] == 0.0
        assert m["max_drawdown_pct"] == 0.0
        assert m["sharpe_ratio"] == 0.0
        assert m["annualized_return_pct"] == 0.0

    def test_all_keys_present(self) -> None:
        """Every call returns all expected metric keys."""
        m = compute_metrics([], [], initial_equity=10_000.0)
        expected_keys = {
            "total_return", "total_return_pct", "final_equity",
            "annualized_return_pct", "max_drawdown", "max_drawdown_pct",
            "num_trades", "num_wins", "num_losses", "win_rate",
            "profit_factor", "sharpe_ratio",
        }
        assert expected_keys.issubset(m.keys())

    def test_all_values_json_serializable(self) -> None:
        curve = [EquityPoint(_ts(i), 10_000.0 + i * 100) for i in range(5)]
        trades = [BacktestTrade(_ts(1), "sell", 100.0, 1.0, 0.1, 0.0, 50.0)]
        m = compute_metrics(trades, curve, initial_equity=10_000.0)
        for k, v in m.items():
            assert isinstance(k, str)
            assert isinstance(v, (int, float))
            assert not math.isnan(v)
            assert not math.isinf(v)


# ---------------------------------------------------------------------------
# Return and drawdown
# ---------------------------------------------------------------------------

class TestMetricsReturnDrawdown:
    def test_total_return_and_drawdown(self) -> None:
        curve = [
            EquityPoint(_ts(0), 10_000.0),
            EquityPoint(_ts(1), 12_000.0),
            EquityPoint(_ts(2), 9_000.0),
            EquityPoint(_ts(3), 11_000.0),
        ]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["total_return"] == 1_000.0
        assert m["total_return_pct"] == 10.0
        assert m["final_equity"] == 11_000.0
        assert m["max_drawdown"] == 3_000.0
        assert m["max_drawdown_pct"] == 25.0

    def test_no_drawdown_monotonic_increase(self) -> None:
        curve = [EquityPoint(_ts(i), 10_000.0 + i * 500) for i in range(5)]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["max_drawdown"] == 0.0
        assert m["max_drawdown_pct"] == 0.0
        assert m["total_return_pct"] == 20.0

    def test_full_drawdown_to_zero(self) -> None:
        curve = [
            EquityPoint(_ts(0), 10_000.0),
            EquityPoint(_ts(1), 5_000.0),
            EquityPoint(_ts(2), 0.0),
        ]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["max_drawdown"] == 10_000.0
        assert m["max_drawdown_pct"] == 100.0
        assert m["total_return_pct"] == -100.0

    def test_negative_return(self) -> None:
        curve = [
            EquityPoint(_ts(0), 10_000.0),
            EquityPoint(_ts(1), 8_000.0),
        ]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["total_return"] == -2_000.0
        assert m["total_return_pct"] == -20.0

    def test_drawdown_multiple_peaks(self) -> None:
        """Max drawdown should track from the highest peak, not most recent."""
        curve = [
            EquityPoint(_ts(0), 10_000.0),
            EquityPoint(_ts(1), 15_000.0),  # peak
            EquityPoint(_ts(2), 14_000.0),  # dd = 1k (6.67%)
            EquityPoint(_ts(3), 14_500.0),
            EquityPoint(_ts(4), 11_000.0),  # dd = 4k from peak 15k (26.67%)
        ]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["max_drawdown"] == 4_000.0
        assert m["max_drawdown_pct"] == pytest.approx(26.6667, abs=0.01)


# ---------------------------------------------------------------------------
# Trade metrics (win rate, profit factor)
# ---------------------------------------------------------------------------

class TestMetricsTrades:
    def test_win_rate_and_profit_factor(self) -> None:
        curve = [EquityPoint(_ts(0), 10_000.0), EquityPoint(_ts(1), 10_500.0)]
        trades = [
            BacktestTrade(_ts(1), "sell", 100.0, 10.0, 1.0, 0.5, 50.0),
            BacktestTrade(_ts(1), "sell", 100.0, 10.0, 1.0, 0.5, -20.0),
            BacktestTrade(_ts(1), "sell", 100.0, 10.0, 1.0, 0.5, 30.0),
        ]
        m = compute_metrics(trades, curve, initial_equity=10_000.0)
        assert m["num_trades"] == 3
        assert m["num_wins"] == 2
        assert m["num_losses"] == 1
        assert m["win_rate"] == pytest.approx(66.67, abs=0.1)
        assert m["profit_factor"] == pytest.approx(4.0, abs=0.01)

    def test_all_wins_profit_factor(self) -> None:
        curve = [EquityPoint(_ts(0), 10_000.0), EquityPoint(_ts(1), 10_100.0)]
        trades = [
            BacktestTrade(_ts(1), "sell", 100.0, 1.0, 0.1, 0.05, 100.0),
        ]
        m = compute_metrics(trades, curve, initial_equity=10_000.0)
        assert m["num_wins"] == 1
        assert m["num_losses"] == 0
        assert m["profit_factor"] == 100.0

    def test_all_losses(self) -> None:
        curve = [EquityPoint(_ts(0), 10_000.0), EquityPoint(_ts(1), 9_500.0)]
        trades = [
            BacktestTrade(_ts(1), "sell", 100.0, 10.0, 0.5, 0.1, -50.0),
            BacktestTrade(_ts(1), "sell", 100.0, 10.0, 0.5, 0.1, -30.0),
        ]
        m = compute_metrics(trades, curve, initial_equity=10_000.0)
        assert m["num_wins"] == 0
        assert m["num_losses"] == 2
        assert m["win_rate"] == 0.0
        assert m["profit_factor"] == 0.0

    def test_zero_pnl_counts_as_loss(self) -> None:
        """A trade with pnl=0 should be counted as a loss (pnl <= 0)."""
        curve = [EquityPoint(_ts(0), 10_000.0), EquityPoint(_ts(1), 10_000.0)]
        trades = [
            BacktestTrade(_ts(1), "sell", 100.0, 10.0, 0.5, 0.1, 0.0),
        ]
        m = compute_metrics(trades, curve, initial_equity=10_000.0)
        assert m["num_trades"] == 1
        assert m["num_wins"] == 0
        assert m["num_losses"] == 1

    def test_ignores_buy_trades(self) -> None:
        curve = [EquityPoint(_ts(0), 10_000.0), EquityPoint(_ts(1), 10_000.0)]
        trades = [
            BacktestTrade(_ts(0), "buy", 100.0, 50.0, 5.0, 2.0, None),
            BacktestTrade(_ts(1), "sell", 102.0, 50.0, 5.1, 2.0, 95.0),
        ]
        m = compute_metrics(trades, curve, initial_equity=10_000.0)
        assert m["num_trades"] == 1
        assert m["num_wins"] == 1
        assert m["win_rate"] == 100.0

    def test_no_trades(self) -> None:
        curve = [EquityPoint(_ts(0), 10_000.0), EquityPoint(_ts(1), 10_000.0)]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["num_trades"] == 0
        assert m["num_wins"] == 0
        assert m["num_losses"] == 0
        assert m["win_rate"] == 0.0
        assert m["profit_factor"] == 0.0


# ---------------------------------------------------------------------------
# Sharpe ratio
# ---------------------------------------------------------------------------

class TestMetricsSharpe:
    def test_flat_equity_zero_sharpe(self) -> None:
        curve = [EquityPoint(_ts(i), 10_000.0) for i in range(5)]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["sharpe_ratio"] == 0.0

    def test_monotonic_increase_positive_sharpe(self) -> None:
        """Steady growth with no volatility → very high Sharpe."""
        curve = [EquityPoint(_ts(i), 10_000.0 + i * 10.0) for i in range(100)]
        m = compute_metrics([], curve, initial_equity=10_000.0, period_hours=1.0)
        assert m["sharpe_ratio"] > 0

    def test_volatile_equity_lower_sharpe(self) -> None:
        """Volatile returns should produce lower Sharpe than steady returns."""
        steady = [EquityPoint(_ts(i), 10_000.0 + i * 10.0) for i in range(50)]
        volatile = [
            EquityPoint(_ts(i), 10_000.0 + i * 10.0 + (100 if i % 2 == 0 else -100))
            for i in range(50)
        ]
        m_steady = compute_metrics([], steady, initial_equity=10_000.0, period_hours=1.0)
        m_volatile = compute_metrics([], volatile, initial_equity=10_000.0, period_hours=1.0)
        assert m_steady["sharpe_ratio"] > m_volatile["sharpe_ratio"]

    def test_sharpe_period_hours_scaling(self) -> None:
        """4h bars should produce different annualized Sharpe than 1h bars."""
        curve = [EquityPoint(_ts(i), 10_000.0 + i * 10.0) for i in range(50)]
        m_1h = compute_metrics([], curve, initial_equity=10_000.0, period_hours=1.0)
        m_4h = compute_metrics([], curve, initial_equity=10_000.0, period_hours=4.0)
        # 1h has more periods/year → higher annualized factor → higher Sharpe
        assert m_1h["sharpe_ratio"] > m_4h["sharpe_ratio"]


# ---------------------------------------------------------------------------
# Annualized return
# ---------------------------------------------------------------------------

class TestMetricsAnnualizedReturn:
    def test_one_year_double(self) -> None:
        """Doubling equity over exactly 1 year → ~100% annualized return."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, tzinfo=timezone.utc)
        curve = [
            EquityPoint(start, 10_000.0),
            EquityPoint(end, 20_000.0),
        ]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["annualized_return_pct"] == pytest.approx(100.0, abs=2.0)

    def test_half_year_20pct(self) -> None:
        """20% gain in 6 months → annualized should be > 20%."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 7, 1, tzinfo=timezone.utc)
        curve = [
            EquityPoint(start, 10_000.0),
            EquityPoint(end, 12_000.0),
        ]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["annualized_return_pct"] > 20.0  # compounded over full year

    def test_zero_time_span_zero_annualized(self) -> None:
        """Same timestamp for start and end → 0 annualized return."""
        curve = [
            EquityPoint(_ts(0), 10_000.0),
            EquityPoint(_ts(0), 12_000.0),
        ]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["annualized_return_pct"] == 0.0

    def test_loss_negative_annualized(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, tzinfo=timezone.utc)
        curve = [
            EquityPoint(start, 10_000.0),
            EquityPoint(end, 8_000.0),
        ]
        m = compute_metrics([], curve, initial_equity=10_000.0)
        assert m["annualized_return_pct"] < 0


# ---------------------------------------------------------------------------
# Integration with engine
# ---------------------------------------------------------------------------

class TestMetricsIntegration:
    def test_from_result_wrapper(self) -> None:
        candles = [
            BacktestCandle(_ts(i), 100.0 - i * 0.3, 101.0, 99.0, 100.0 - i * 0.3, 1000.0)
            for i in range(60)
        ]
        config = RsiMaConfig(rsi_buy_threshold=25.0, rsi_sell_threshold=75.0)
        bt_result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        m = compute_metrics_from_result(bt_result, period_hours=1.0)
        assert "total_return" in m
        assert "total_return_pct" in m
        assert "max_drawdown" in m
        assert "max_drawdown_pct" in m
        assert "num_trades" in m
        assert "win_rate" in m
        assert "sharpe_ratio" in m
        assert "profit_factor" in m
        assert "final_equity" in m
        assert "annualized_return_pct" in m
        for k, v in m.items():
            assert isinstance(k, str)
            assert isinstance(v, (int, float))
