"""
Synchronous backtest engine (Phase 6.1 + 17.3 sentiment filter).

Signal generation + execution loop with fees and slippage.
Strategy: RSI + MA (buy when RSI < buy_threshold and price > MA;
sell when RSI > sell_threshold or stop loss / take profit hit).

When ``config.sentiment_filter`` is provided and enabled, new long entries
are additionally gated by the aggregate sentiment over the configured
lookback window (Phase 17.3).  Exits are never gated.
"""

from typing import Sequence

from app.schemas.strategy_config import RsiMaConfig
from app.services.backtest.indicators import rsi, sma
from app.services.backtest.types import (
    BacktestCandle,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)
from app.services.sentiment.filter import (
    SentimentSample,
    evaluate_sentiment_gate,
)


def run_backtest_rsi_ma(
    candles: list[BacktestCandle],
    config: RsiMaConfig,
    initial_equity: float = 10_000.0,
    *,
    sentiment_samples: Sequence[SentimentSample] | None = None,
) -> BacktestResult:
    """
    Run a synchronous backtest with RSI+MA strategy.

    Candles must be sorted by timestamp ascending and have at least
    max(rsi_period, ma_period) + 1 bars. Fees and slippage are applied
    on each trade.

    Returns trades and equity curve (one point per bar after warmup, plus
    after each trade for accuracy).
    """
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if not candles:
        return BacktestResult(
            trades=[],
            equity_curve=[],
            initial_equity=initial_equity,
            final_equity=initial_equity,
        )

    closes = [c.close for c in candles]
    period_rsi = config.rsi_period
    period_ma = config.ma_period
    warmup = max(period_rsi, period_ma)
    if len(closes) <= warmup:
        return BacktestResult(
            trades=[],
            equity_curve=[EquityPoint(candles[-1].timestamp, initial_equity)],
            initial_equity=initial_equity,
            final_equity=initial_equity,
        )

    rsi_series = rsi(closes, period_rsi)
    ma_series = sma(closes, period_ma)

    trades: list[BacktestTrade] = []
    equity_curve: list[EquityPoint] = []

    cash = initial_equity
    position = 0.0
    entry_price = 0.0  # execution price at entry (after slippage)
    entry_fee = 0.0
    entry_slippage = 0.0

    fee_rate = config.fee_rate
    slippage_rate = config.slippage_rate
    buy_threshold = config.rsi_buy_threshold
    sell_threshold = config.rsi_sell_threshold
    stop_loss_pct = config.stop_loss_pct
    take_profit_pct = config.take_profit_pct
    position_size_pct = config.position_size_pct

    sentiment_cfg = config.sentiment_filter
    samples_seq: Sequence[SentimentSample] = sentiment_samples or ()

    def _equity(bar_close: float) -> float:
        return cash + position * bar_close

    for i in range(warmup, len(candles)):
        c = candles[i]
        rsi_val = rsi_series[i]
        ma_val = ma_series[i]
        if rsi_val is None or ma_val is None:
            equity_curve.append(EquityPoint(c.timestamp, _equity(c.close)))
            continue

        # --- Position open: check SL/TP then optional signal sell at close ---
        if position > 0:
            sl_price = entry_price * (1.0 - stop_loss_pct / 100.0)
            tp_price = entry_price * (1.0 + take_profit_pct / 100.0)
            exit_price_raw: float | None = None
            if c.low <= sl_price:
                exit_price_raw = sl_price
            elif c.high >= tp_price:
                exit_price_raw = tp_price
            elif rsi_val >= sell_threshold:
                exit_price_raw = c.close

            if exit_price_raw is not None:
                # Execute sell
                exec_price = exit_price_raw * (1.0 - slippage_rate)
                revenue = position * exec_price
                fee = revenue * fee_rate
                slippage_cost = position * exit_price_raw * slippage_rate
                cash += revenue - fee
                entry_cost = position * entry_price * (1.0 + fee_rate) + entry_fee + entry_slippage
                pnl = (revenue - fee) - entry_cost
                trades.append(
                    BacktestTrade(
                        timestamp=c.timestamp,
                        side="sell",
                        price=exec_price,
                        quantity=position,
                        fee=fee,
                        slippage=slippage_cost,
                        pnl=pnl,
                    )
                )
                position = 0.0
                equity_curve.append(EquityPoint(c.timestamp, _equity(exec_price)))
                # Continue to possibly buy at same bar close (we use close for new signal)
                # So we don't buy the same bar we sold; we only evaluate buy when flat at bar start
                equity_curve.append(EquityPoint(c.timestamp, cash))
            else:
                equity_curve.append(EquityPoint(c.timestamp, _equity(c.close)))

        # --- Flat: check buy signal at close ---
        if position <= 0 and rsi_val < buy_threshold and c.close > ma_val:
            # Phase 17.3 sentiment gate (only applied to NEW long entries).
            if sentiment_cfg is not None and sentiment_cfg.enabled:
                gate = evaluate_sentiment_gate(
                    samples_seq, as_of=c.timestamp, config=sentiment_cfg
                )
                if not gate.allow_long:
                    equity_curve.append(EquityPoint(c.timestamp, _equity(c.close)))
                    continue
            equity_before = cash
            notional = equity_before * position_size_pct
            if notional <= 0:
                equity_curve.append(EquityPoint(c.timestamp, _equity(c.close)))
                continue
            exec_price = c.close * (1.0 + slippage_rate)
            quantity = notional / exec_price
            fee = quantity * exec_price * fee_rate
            slippage_cost = quantity * c.close * slippage_rate
            cost_total = quantity * exec_price + fee
            if cost_total > cash:
                quantity = cash / (exec_price * (1.0 + fee_rate))
                fee = quantity * exec_price * fee_rate
                slippage_cost = quantity * c.close * slippage_rate
                cost_total = quantity * exec_price + fee
            if quantity <= 0:
                equity_curve.append(EquityPoint(c.timestamp, cash))
                continue
            cash -= cost_total
            position = quantity
            entry_price = exec_price
            entry_fee = fee
            entry_slippage = slippage_cost
            trades.append(
                BacktestTrade(
                    timestamp=c.timestamp,
                    side="buy",
                    price=exec_price,
                    quantity=quantity,
                    fee=fee,
                    slippage=slippage_cost,
                    pnl=None,
                )
            )
            equity_curve.append(EquityPoint(c.timestamp, _equity(c.close)))
        elif position <= 0:
            equity_curve.append(EquityPoint(c.timestamp, _equity(c.close)))

    final_equity = _equity(candles[-1].close) if candles else cash
    return BacktestResult(
        trades=trades,
        equity_curve=equity_curve,
        initial_equity=initial_equity,
        final_equity=final_equity,
    )
