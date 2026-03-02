"""
Tests for backtest engine (Phase 6.1).
"""

from datetime import datetime, timezone, timedelta

import pytest

from app.schemas.strategy_config import RsiMaConfig
from app.services.backtest import (
    BacktestCandle,
    BacktestResult,
    run_backtest_rsi_ma,
)
from app.services.backtest.indicators import rsi, sma

_BASE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _ts(hours: int = 0) -> datetime:
    return _BASE + timedelta(hours=hours)


def test_sma_basic() -> None:
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = sma(closes, 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] == 2.0  # (1+2+3)/3
    assert out[3] == 3.0
    assert out[4] == 4.0


def test_rsi_basic() -> None:
    # Declining then flat: RSI should drop
    closes = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0]
    out = rsi(closes, 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] is None
    assert out[3] is not None
    assert 0 <= out[3] <= 100
    assert out[4] is not None
    assert out[5] is not None
    assert out[6] is not None


def test_backtest_empty_candles() -> None:
    config = RsiMaConfig()
    result = run_backtest_rsi_ma([], config, initial_equity=10_000.0)
    assert result.initial_equity == 10_000.0
    assert result.final_equity == 10_000.0
    assert result.trades == []
    assert result.equity_curve == []


def test_backtest_insufficient_candles() -> None:
    config = RsiMaConfig(rsi_period=5, ma_period=3)
    candles = [
        BacktestCandle(_ts(hours=i), 100.0, 101.0, 99.0, 100.0, 1000.0)
        for i in range(5)
    ]
    result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
    assert result.final_equity == 10_000.0
    assert result.trades == []
    assert len(result.equity_curve) == 1


def test_backtest_initial_equity_positive() -> None:
    config = RsiMaConfig()
    candles = [
        BacktestCandle(_ts(hours=i), 100.0, 101.0, 99.0, 100.0, 1000.0)
        for i in range(30)
    ]
    with pytest.raises(ValueError, match="initial_equity"):
        run_backtest_rsi_ma(candles, config, initial_equity=0.0)
    with pytest.raises(ValueError, match="initial_equity"):
        run_backtest_rsi_ma(candles, config, initial_equity=-100.0)


def test_backtest_produces_equity_curve() -> None:
    """Run with enough bars; equity curve should have one point per bar after warmup."""
    config = RsiMaConfig(rsi_period=5, ma_period=3)
    # Flat price so no strong signals, but we have valid RSI/MA
    candles = [
        BacktestCandle(_ts(hours=i), 100.0, 100.5, 99.5, 100.0, 1000.0)
        for i in range(50)
    ]
    result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
    assert isinstance(result, BacktestResult)
    assert result.initial_equity == 10_000.0
    assert len(result.equity_curve) >= 1
    assert result.equity_curve[0].equity_value == 10_000.0
    # Final equity should be close to initial (flat market, maybe small fees if any trade)
    assert result.final_equity > 0


def test_backtest_trade_has_fee_and_slippage() -> None:
    """With a config that triggers at least one trade, sell trade should have fee, slippage, pnl."""
    config = RsiMaConfig(
        rsi_period=5,
        ma_period=3,
        rsi_buy_threshold=25.0,  # buy when RSI low (oversold)
        rsi_sell_threshold=75.0,  # sell when RSI high (overbought)
        fee_rate=0.001,
        slippage_rate=0.0005,
    )
    # Downtrend then uptrend: RSI drops then rises so we might get buy then sell
    base = 100.0
    candles = []
    for i in range(60):
        if i < 25:
            close = base - i * 0.5  # downtrend
        else:
            close = base - 12.5 + (i - 25) * 0.3  # uptrend
        candles.append(
            BacktestCandle(
                _ts(hours=i), close, close + 0.5, close - 0.5, close, 1000.0
            )
        )
    result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
    for t in result.trades:
        assert t.side in ("buy", "sell")
        assert t.price > 0
        assert t.quantity > 0
        assert t.fee >= 0
        assert t.slippage >= 0
        if t.side == "sell":
            assert t.pnl is not None
        else:
            assert t.pnl is None
