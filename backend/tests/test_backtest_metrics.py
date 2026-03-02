"""
Tests for backtest metrics module (Phase 6.2).
"""

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


def test_compute_metrics_empty_equity_uses_initial_final() -> None:
    """With no equity curve, final_equity should equal initial_equity."""
    m = compute_metrics([], [], initial_equity=10_000.0)
    assert m["final_equity"] == 10_000.0
    assert m["total_return"] == 0.0
    assert m["total_return_pct"] == 0.0
    assert m["max_drawdown"] == 0.0
    assert m["num_trades"] == 0
    assert m["win_rate"] == 0.0
    assert m["sharpe_ratio"] == 0.0


def test_compute_metrics_zero_initial_equity() -> None:
    """Zero initial equity returns all zeros."""
    m = compute_metrics(
        [],
        [EquityPoint(_ts(0), 100.0)],
        initial_equity=0.0,
    )
    assert m["total_return"] == 0.0
    assert m["final_equity"] == 0.0
    assert m["num_trades"] == 0


def test_compute_metrics_total_return_and_drawdown() -> None:
    """Known equity curve: total return and max drawdown."""
    # Peak 12k, then drop to 9k, then 11k
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
    assert m["max_drawdown"] == 3_000.0  # 12k -> 9k
    assert m["max_drawdown_pct"] == 25.0  # 3000/12000 * 100


def test_compute_metrics_win_rate_and_profit_factor() -> None:
    """Known closed trades: win rate and profit factor."""
    curve = [
        EquityPoint(_ts(0), 10_000.0),
        EquityPoint(_ts(1), 10_500.0),
    ]
    trades = [
        BacktestTrade(_ts(1), "sell", 100.0, 10.0, 1.0, 0.5, 50.0),   # win
        BacktestTrade(_ts(1), "sell", 100.0, 10.0, 1.0, 0.5, -20.0),   # loss
        BacktestTrade(_ts(1), "sell", 100.0, 10.0, 1.0, 0.5, 30.0),   # win
    ]
    m = compute_metrics(trades, curve, initial_equity=10_000.0)
    assert m["num_trades"] == 3
    assert m["num_wins"] == 2
    assert m["num_losses"] == 1
    assert m["win_rate"] == pytest.approx(66.67, abs=0.1)
    # profit factor = gross profit / gross loss = (50+30) / 20 = 4.0
    assert m["profit_factor"] == pytest.approx(4.0, abs=0.01)


def test_compute_metrics_all_losses_profit_factor_zero() -> None:
    """When gross_loss is 0 (no losing trades), profit factor is 0 or gross_profit."""
    curve = [EquityPoint(_ts(0), 10_000.0), EquityPoint(_ts(1), 10_100.0)]
    trades = [
        BacktestTrade(_ts(1), "sell", 100.0, 1.0, 0.1, 0.05, 100.0),
    ]
    m = compute_metrics(trades, curve, initial_equity=10_000.0)
    assert m["num_trades"] == 1
    assert m["num_wins"] == 1
    assert m["num_losses"] == 0
    assert m["profit_factor"] == 100.0  # gross_loss=0 -> we return gross_profit


def test_compute_metrics_ignores_buy_trades() -> None:
    """Only sell trades with pnl count toward num_trades / win_rate."""
    curve = [EquityPoint(_ts(0), 10_000.0), EquityPoint(_ts(1), 10_000.0)]
    trades = [
        BacktestTrade(_ts(0), "buy", 100.0, 50.0, 5.0, 2.0, None),
        BacktestTrade(_ts(1), "sell", 102.0, 50.0, 5.1, 2.0, 95.0),
    ]
    m = compute_metrics(trades, curve, initial_equity=10_000.0)
    assert m["num_trades"] == 1
    assert m["num_wins"] == 1
    assert m["win_rate"] == 100.0


def test_compute_metrics_from_result_integration() -> None:
    """compute_metrics_from_result on real BacktestResult from engine."""
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
    # All values JSON-serializable
    for k, v in m.items():
        assert isinstance(k, str)
        assert isinstance(v, (int, float))


def test_compute_metrics_sharpe_flat_equity_zero() -> None:
    """Flat equity curve -> zero volatility -> sharpe 0."""
    curve = [EquityPoint(_ts(i), 10_000.0) for i in range(5)]
    m = compute_metrics([], curve, initial_equity=10_000.0)
    assert m["sharpe_ratio"] == 0.0


def test_compute_metrics_single_equity_point() -> None:
    """Single point equity curve: return correct, drawdown 0, sharpe 0."""
    curve = [EquityPoint(_ts(0), 11_000.0)]
    m = compute_metrics([], curve, initial_equity=10_000.0)
    assert m["total_return"] == 1_000.0
    assert m["total_return_pct"] == 10.0
    assert m["max_drawdown"] == 0.0
    assert m["max_drawdown_pct"] == 0.0
    assert m["sharpe_ratio"] == 0.0
    assert m["annualized_return_pct"] == 0.0
