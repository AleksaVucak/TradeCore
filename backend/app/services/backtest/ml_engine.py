"""
ML Signal backtest engine (Phase 16.3).

Replaces indicator-based signal generation with trained ML model predictions.
Execution mechanics (fees, slippage, position sizing, SL/TP) mirror the
RSI+MA engine exactly for consistent comparison.
"""

from __future__ import annotations

import os
from typing import Sequence

import joblib

from app.schemas.strategy_config import MlSignalConfig
from app.services.backtest.types import (
    BacktestCandle,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)
from app.services.ml.signal_training import compute_all_catalog_features
from app.services.sentiment.filter import (
    SentimentSample,
    evaluate_sentiment_gate,
)


def _load_signal_model(artifact_path: str) -> tuple:
    """Load a trained signal model artifact from disk.

    Returns (classifier, feature_keys) where feature_keys is the ordered
    list of feature names the model was trained on.

    Raises FileNotFoundError if the artifact does not exist.
    Raises ValueError if the artifact is missing required keys.
    """
    if not os.path.isfile(artifact_path):
        raise FileNotFoundError(
            f"ML model artifact not found at {artifact_path}. "
            "Ensure the model has been trained and the artifact path is correct."
        )
    data = joblib.load(artifact_path)
    if "model" not in data or "feature_keys" not in data:
        raise ValueError(
            f"Invalid signal model artifact at {artifact_path}. "
            "Expected keys 'model' and 'feature_keys'."
        )
    return data["model"], data["feature_keys"]


def _compute_probabilities(
    candles: list[BacktestCandle],
    clf,
    feature_names: list[str],
) -> list[float | None]:
    """Compute per-bar probability of upward price movement.

    Builds the full feature matrix from OHLCV data (using the same
    computation as training), then runs batch inference with the
    classifier's ``predict_proba``.

    Returns a list aligned with *candles* (same length).  Bars where any
    required feature is ``None`` (warmup period) receive ``None``.
    """
    n = len(candles)
    if n == 0:
        return []

    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]

    all_features = compute_all_catalog_features(opens, highs, lows, closes, volumes)

    # Determine which column of predict_proba corresponds to class 1
    classes = list(clf.classes_)
    if 1 not in classes:
        raise ValueError(
            f"Trained model does not contain class 1 (upward movement). "
            f"Model classes: {classes}"
        )
    class_1_idx = classes.index(1)

    probabilities: list[float | None] = [None] * n

    usable_indices: list[int] = []
    X: list[list[float]] = []

    for i in range(n):
        vals = [all_features[f][i] for f in feature_names]
        if any(v is None for v in vals):
            continue
        usable_indices.append(i)
        X.append([float(v) for v in vals])  # type: ignore[arg-type]

    if X:
        proba_matrix = clf.predict_proba(X)
        for idx, proba_row in zip(usable_indices, proba_matrix):
            probabilities[idx] = float(proba_row[class_1_idx])

    return probabilities


def run_backtest_ml_signal(
    candles: list[BacktestCandle],
    config: MlSignalConfig,
    *,
    artifact_path: str,
    initial_equity: float = 10_000.0,
    sentiment_samples: Sequence[SentimentSample] | None = None,
) -> BacktestResult:
    """Run a synchronous backtest using an ML signal strategy.

    The trained model produces a probability of upward price movement at
    each bar.  Trading rules:

    * **Enter long** when flat and ``probability >= long_threshold``.
    * **Exit** when in position and ``probability <= exit_threshold``,
      or when a stop-loss / take-profit level is breached intra-bar.

    Execution mechanics (fees, slippage, position sizing, SL/TP priority)
    are identical to :func:`run_backtest_rsi_ma` so that results from the
    two strategy types are directly comparable.
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

    clf, trained_feature_keys = _load_signal_model(artifact_path)

    if set(config.features) != set(trained_feature_keys):
        mismatched = set(config.features).symmetric_difference(set(trained_feature_keys))
        raise ValueError(
            f"Strategy config features do not match the model's training features. "
            f"Mismatched: {sorted(mismatched)}"
        )

    # Always use the training feature order for prediction consistency
    feature_names = trained_feature_keys

    probabilities = _compute_probabilities(candles, clf, feature_names)

    usable_count = sum(1 for p in probabilities if p is not None)
    if usable_count == 0:
        return BacktestResult(
            trades=[],
            equity_curve=[EquityPoint(candles[-1].timestamp, initial_equity)],
            initial_equity=initial_equity,
            final_equity=initial_equity,
        )

    # ------------------------------------------------------------------
    # Trading loop — mirrors RSI+MA engine execution mechanics exactly
    # ------------------------------------------------------------------
    trades: list[BacktestTrade] = []
    equity_curve: list[EquityPoint] = []

    cash = initial_equity
    position = 0.0
    entry_price = 0.0
    entry_fee = 0.0
    entry_slippage = 0.0

    fee_rate = config.fee_rate
    slippage_rate = config.slippage_rate
    long_threshold = config.long_threshold
    exit_threshold = config.exit_threshold
    stop_loss_pct = config.stop_loss_pct
    take_profit_pct = config.take_profit_pct
    position_size_pct = config.position_size_pct

    sentiment_cfg = config.sentiment_filter
    samples_seq: Sequence[SentimentSample] = sentiment_samples or ()

    def _equity(bar_close: float) -> float:
        return cash + position * bar_close

    for i in range(len(candles)):
        c = candles[i]
        proba = probabilities[i]

        if proba is None:
            equity_curve.append(EquityPoint(c.timestamp, _equity(c.close)))
            continue

        # --- Position open: check SL/TP then ML signal exit ---
        if position > 0:
            sl_price = entry_price * (1.0 - stop_loss_pct / 100.0)
            tp_price = entry_price * (1.0 + take_profit_pct / 100.0)
            exit_price_raw: float | None = None

            # SL checked first (low), then TP (high), then signal at close
            if c.low <= sl_price:
                exit_price_raw = sl_price
            elif c.high >= tp_price:
                exit_price_raw = tp_price
            elif proba <= exit_threshold:
                exit_price_raw = c.close

            if exit_price_raw is not None:
                exec_price = exit_price_raw * (1.0 - slippage_rate)
                revenue = position * exec_price
                fee = revenue * fee_rate
                slippage_cost = position * exit_price_raw * slippage_rate
                cash += revenue - fee
                entry_cost = (
                    position * entry_price * (1.0 + fee_rate)
                    + entry_fee
                    + entry_slippage
                )
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
                equity_curve.append(EquityPoint(c.timestamp, cash))
            else:
                equity_curve.append(EquityPoint(c.timestamp, _equity(c.close)))

        # --- Flat: check ML buy signal ---
        if position <= 0 and proba >= long_threshold:
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
