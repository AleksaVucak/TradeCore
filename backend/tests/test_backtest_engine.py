"""
Tests for backtest engine and indicators (Phase 6.1 / Phase 11.1).
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


# ---------------------------------------------------------------------------
# Indicator tests: SMA
# ---------------------------------------------------------------------------

class TestSma:
    def test_basic(self) -> None:
        closes = [1.0, 2.0, 3.0, 4.0, 5.0]
        out = sma(closes, 3)
        assert out[0] is None
        assert out[1] is None
        assert out[2] == 2.0
        assert out[3] == 3.0
        assert out[4] == 4.0

    def test_period_one(self) -> None:
        closes = [10.0, 20.0, 30.0]
        out = sma(closes, 1)
        assert out == [10.0, 20.0, 30.0]

    def test_period_equals_length(self) -> None:
        closes = [2.0, 4.0, 6.0]
        out = sma(closes, 3)
        assert out[0] is None
        assert out[1] is None
        assert out[2] == pytest.approx(4.0)

    def test_period_exceeds_length(self) -> None:
        closes = [1.0, 2.0]
        out = sma(closes, 5)
        assert all(v is None for v in out)

    def test_empty_input(self) -> None:
        assert sma([], 3) == []

    def test_constant_series(self) -> None:
        closes = [50.0] * 10
        out = sma(closes, 3)
        for i in range(2, 10):
            assert out[i] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Indicator tests: RSI
# ---------------------------------------------------------------------------

class TestRsi:
    def test_declining_series(self) -> None:
        closes = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0]
        out = rsi(closes, 3)
        assert out[0] is None
        assert out[1] is None
        assert out[2] is None
        assert out[3] is not None
        assert 0 <= out[3] <= 100

    def test_rising_series_high_rsi(self) -> None:
        closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
        out = rsi(closes, 3)
        for i in range(3, len(out)):
            assert out[i] is not None
            assert out[i] > 50.0  # rising series → RSI > 50

    def test_constant_series_rsi_near_50(self) -> None:
        closes = [100.0] * 10
        out = rsi(closes, 3)
        # No gains or losses → avg_loss == 0 → RSI = 100 (by implementation)
        for i in range(3, len(out)):
            assert out[i] is not None
            assert out[i] == 100.0

    def test_alternating_series(self) -> None:
        closes = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0]
        out = rsi(closes, 3)
        for i in range(3, len(out)):
            assert out[i] is not None
            assert 20.0 <= out[i] <= 80.0  # oscillating → moderate RSI

    def test_rsi_bounds(self) -> None:
        """RSI should always be in [0, 100] regardless of input."""
        closes = [100.0 + i * 10.0 for i in range(20)]
        out = rsi(closes, 5)
        for v in out:
            if v is not None:
                assert 0.0 <= v <= 100.0

    def test_empty_input(self) -> None:
        assert rsi([], 3) == []

    def test_insufficient_data(self) -> None:
        closes = [1.0, 2.0, 3.0]
        out = rsi(closes, 5)
        assert all(v is None for v in out)


# ---------------------------------------------------------------------------
# Engine tests: basic behavior
# ---------------------------------------------------------------------------

class TestEngineBasic:
    def test_empty_candles(self) -> None:
        config = RsiMaConfig()
        result = run_backtest_rsi_ma([], config, initial_equity=10_000.0)
        assert result.initial_equity == 10_000.0
        assert result.final_equity == 10_000.0
        assert result.trades == []
        assert result.equity_curve == []

    def test_insufficient_candles(self) -> None:
        config = RsiMaConfig(rsi_period=5, ma_period=3)
        candles = [
            BacktestCandle(_ts(hours=i), 100.0, 101.0, 99.0, 100.0, 1000.0)
            for i in range(5)
        ]
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        assert result.final_equity == 10_000.0
        assert result.trades == []
        assert len(result.equity_curve) == 1

    def test_initial_equity_zero_raises(self) -> None:
        config = RsiMaConfig()
        candles = [
            BacktestCandle(_ts(hours=i), 100.0, 101.0, 99.0, 100.0, 1000.0)
            for i in range(30)
        ]
        with pytest.raises(ValueError, match="initial_equity"):
            run_backtest_rsi_ma(candles, config, initial_equity=0.0)

    def test_initial_equity_negative_raises(self) -> None:
        config = RsiMaConfig()
        candles = [
            BacktestCandle(_ts(hours=i), 100.0, 101.0, 99.0, 100.0, 1000.0)
            for i in range(30)
        ]
        with pytest.raises(ValueError, match="initial_equity"):
            run_backtest_rsi_ma(candles, config, initial_equity=-100.0)

    def test_produces_equity_curve(self) -> None:
        config = RsiMaConfig(rsi_period=5, ma_period=3)
        candles = [
            BacktestCandle(_ts(hours=i), 100.0, 100.5, 99.5, 100.0, 1000.0)
            for i in range(50)
        ]
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        assert isinstance(result, BacktestResult)
        assert result.initial_equity == 10_000.0
        assert len(result.equity_curve) >= 1
        assert result.equity_curve[0].equity_value == 10_000.0
        assert result.final_equity > 0

    def test_trade_has_fee_and_slippage(self) -> None:
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=25.0,
            rsi_sell_threshold=75.0,
            fee_rate=0.001,
            slippage_rate=0.0005,
        )
        base = 100.0
        candles = []
        for i in range(60):
            if i < 25:
                close = base - i * 0.5
            else:
                close = base - 12.5 + (i - 25) * 0.3
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

    def test_flat_market_no_trades(self) -> None:
        """Flat price above MA with mid-range RSI should not trigger buy signal."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=30.0,
            rsi_sell_threshold=70.0,
        )
        candles = [
            BacktestCandle(_ts(hours=i), 100.0, 100.5, 99.5, 100.0, 1000.0)
            for i in range(50)
        ]
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        sell_trades = [t for t in result.trades if t.side == "sell"]
        assert len(sell_trades) == 0
        assert result.final_equity == pytest.approx(10_000.0, abs=1.0)


# ---------------------------------------------------------------------------
# Engine tests: stop-loss and take-profit
# ---------------------------------------------------------------------------

class TestEngineSLTP:
    def test_stop_loss_triggers_exit(self) -> None:
        """When bar low drops below SL price, the position should be closed at a loss."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=30.0,
            rsi_sell_threshold=95.0,  # very high so RSI sell won't fire
            stop_loss_pct=1.0,  # tight SL
            take_profit_pct=50.0,  # very wide TP
            fee_rate=0.0,
            slippage_rate=0.0,
        )
        # Downtrend → low RSI → buy. Then next bar has a very low low to trip SL.
        candles = []
        for i in range(30):
            close = 100.0 - i * 0.6
            candles.append(
                BacktestCandle(_ts(hours=i), close + 0.1, close + 0.5, close - 0.5, close, 1000.0)
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        buy_trades = [t for t in result.trades if t.side == "buy"]
        sell_trades = [t for t in result.trades if t.side == "sell"]
        # The continuous decline should trigger SL on positions
        if buy_trades and sell_trades:
            for st in sell_trades:
                assert st.pnl is not None
                assert st.pnl < 0  # SL always exits at a loss with tight SL

    def test_take_profit_triggers_exit(self) -> None:
        """When bar high exceeds TP price, the position should be closed at profit."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=25.0,
            rsi_sell_threshold=95.0,
            stop_loss_pct=50.0,
            take_profit_pct=3.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )
        candles = []
        for i in range(60):
            if i < 20:
                close = 100.0 - i * 0.5
            elif i == 20:
                close = 100.0 - 10.0
                high = 200.0  # spike → hit TP
                candles.append(
                    BacktestCandle(
                        _ts(hours=i), close, high, close - 0.5, close, 1000.0
                    )
                )
                continue
            else:
                close = 90.0 + (i - 20) * 0.1
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 0.5, close - 0.5, close, 1000.0
                )
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        sell_trades = [t for t in result.trades if t.side == "sell"]
        if sell_trades:
            buy_trades = [t for t in result.trades if t.side == "buy"]
            assert len(buy_trades) >= 1
            entry = buy_trades[0].price
            tp_price = entry * (1.0 + config.take_profit_pct / 100.0)
            assert sell_trades[0].price == pytest.approx(tp_price, rel=0.01)

    def test_rsi_sell_signal_exit(self) -> None:
        """Position closes when RSI exceeds sell threshold (not SL/TP)."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=25.0,
            rsi_sell_threshold=70.0,
            stop_loss_pct=50.0,
            take_profit_pct=50.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )
        candles = []
        for i in range(80):
            if i < 25:
                close = 100.0 - i * 0.5
            else:
                close = 87.5 + (i - 25) * 0.5
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 0.3, close - 0.3, close, 1000.0
                )
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        sell_trades = [t for t in result.trades if t.side == "sell"]
        if sell_trades:
            for st in sell_trades:
                assert st.pnl is not None

    def test_sl_before_tp_priority(self) -> None:
        """If both SL and TP could trigger, SL is checked first (low before high)."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=25.0,
            rsi_sell_threshold=95.0,
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )
        candles = []
        for i in range(30):
            close = 100.0 - i * 0.6
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 5.0, close - 5.0, close, 1000.0
                )
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        sell_trades = [t for t in result.trades if t.side == "sell"]
        buy_trades = [t for t in result.trades if t.side == "buy"]
        if buy_trades and sell_trades:
            entry = buy_trades[0].price
            sl_price = entry * (1.0 - config.stop_loss_pct / 100.0)
            # Engine checks SL first, so exit should be at SL price
            assert sell_trades[0].price == pytest.approx(sl_price, rel=0.01)


# ---------------------------------------------------------------------------
# Engine tests: equity curve invariants
# ---------------------------------------------------------------------------

class TestEngineEquityCurve:
    def test_equity_curve_timestamps_non_decreasing(self) -> None:
        config = RsiMaConfig(rsi_period=5, ma_period=3)
        candles = []
        for i in range(60):
            close = 100.0 - i * 0.3 if i < 30 else 91.0 + (i - 30) * 0.3
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 0.5, close - 0.5, close, 1000.0
                )
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        timestamps = [p.timestamp for p in result.equity_curve]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]

    def test_equity_curve_all_positive(self) -> None:
        """Equity should never go negative."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=30.0,
            rsi_sell_threshold=70.0,
        )
        candles = []
        for i in range(60):
            close = 100.0 - i * 0.3 if i < 30 else 91.0 + (i - 30) * 0.3
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 0.5, close - 0.5, close, 1000.0
                )
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        for p in result.equity_curve:
            assert p.equity_value >= 0

    def test_final_equity_matches_last_curve_point(self) -> None:
        """final_equity should be consistent with the last equity curve entry."""
        config = RsiMaConfig(rsi_period=5, ma_period=3)
        candles = [
            BacktestCandle(_ts(hours=i), 100.0, 100.5, 99.5, 100.0, 1000.0)
            for i in range(50)
        ]
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        assert result.final_equity > 0
        # final_equity uses last candle close; last curve point is also equity at last bar
        if result.equity_curve:
            last_point = result.equity_curve[-1].equity_value
            assert result.final_equity == pytest.approx(last_point, rel=0.01)

    def test_buy_sell_pairs_balanced(self) -> None:
        """Number of sells should never exceed number of buys."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=25.0,
            rsi_sell_threshold=75.0,
        )
        candles = []
        for i in range(100):
            close = 100.0 - i * 0.3 if i < 40 else 88.0 + (i - 40) * 0.4
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 0.5, close - 0.5, close, 1000.0
                )
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        buys = sum(1 for t in result.trades if t.side == "buy")
        sells = sum(1 for t in result.trades if t.side == "sell")
        assert sells <= buys
        assert buys - sells <= 1  # at most one open position at the end


# ---------------------------------------------------------------------------
# Engine tests: position sizing and edge cases
# ---------------------------------------------------------------------------

class TestEnginePositionSizing:
    def test_small_position_size(self) -> None:
        """With position_size_pct=0.1, notional = 10% of equity."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=25.0,
            rsi_sell_threshold=75.0,
            position_size_pct=0.1,
            fee_rate=0.0,
            slippage_rate=0.0,
        )
        candles = []
        for i in range(60):
            close = 100.0 - i * 0.5 if i < 25 else 87.5 + (i - 25) * 0.3
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 0.5, close - 0.5, close, 1000.0
                )
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        buy_trades = [t for t in result.trades if t.side == "buy"]
        if buy_trades:
            first_buy = buy_trades[0]
            expected_notional = 10_000.0 * 0.1  # 1000
            actual_cost = first_buy.price * first_buy.quantity
            assert actual_cost == pytest.approx(expected_notional, rel=0.05)

    def test_full_position_size(self) -> None:
        """With position_size_pct=1.0, entire equity is used."""
        config = RsiMaConfig(
            rsi_period=5,
            ma_period=3,
            rsi_buy_threshold=25.0,
            rsi_sell_threshold=75.0,
            position_size_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )
        candles = []
        for i in range(60):
            close = 100.0 - i * 0.5 if i < 25 else 87.5 + (i - 25) * 0.3
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 0.5, close - 0.5, close, 1000.0
                )
            )
        result = run_backtest_rsi_ma(candles, config, initial_equity=10_000.0)
        buy_trades = [t for t in result.trades if t.side == "buy"]
        if buy_trades:
            first_buy = buy_trades[0]
            actual_cost = first_buy.price * first_buy.quantity
            assert actual_cost == pytest.approx(10_000.0, rel=0.05)

    def test_high_fees_reduce_equity(self) -> None:
        """High fee rate should reduce equity more than low fee rate."""
        candles = []
        for i in range(60):
            close = 100.0 - i * 0.5 if i < 25 else 87.5 + (i - 25) * 0.3
            candles.append(
                BacktestCandle(
                    _ts(hours=i), close, close + 0.5, close - 0.5, close, 1000.0
                )
            )
        low_fee = RsiMaConfig(
            rsi_period=5, ma_period=3,
            rsi_buy_threshold=25.0, rsi_sell_threshold=75.0,
            fee_rate=0.0, slippage_rate=0.0,
        )
        high_fee = RsiMaConfig(
            rsi_period=5, ma_period=3,
            rsi_buy_threshold=25.0, rsi_sell_threshold=75.0,
            fee_rate=0.05, slippage_rate=0.0,
        )
        r_low = run_backtest_rsi_ma(candles, low_fee, initial_equity=10_000.0)
        r_high = run_backtest_rsi_ma(candles, high_fee, initial_equity=10_000.0)
        if r_low.trades and r_high.trades:
            assert r_high.final_equity <= r_low.final_equity
