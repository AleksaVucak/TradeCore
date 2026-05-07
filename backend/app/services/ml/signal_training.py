"""
Training pipeline for ML signal strategy models (Phase 16.2).

Trains a binary classifier that predicts the probability of upward
price movement over a configurable horizon.  The model artifact is
stored on disk and tracked in MLModelMetadata so it can be referenced
by MlSignalConfig.model_id.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import (
    RandomizedSearchCV,
    StratifiedKFold,
    train_test_split,
)
from sqlalchemy.orm import Session

from app.models.candle import Candle
from app.models.ml_model_metadata import MLModelMetadata
from app.services.backtest.indicators import rsi, sma

ARTIFACT_DIR = Path(os.environ.get("ML_ARTIFACT_DIR", "/app/ml_artifacts"))

DEFAULT_SIGNAL_PARAM_GRID: dict[str, list] = {
    "n_estimators": [100, 200, 300, 500],
    "max_depth": [3, 4, 5, 6, 8],
    "learning_rate": [0.01, 0.05, 0.1, 0.2],
    "min_samples_split": [2, 5, 10],
    "min_samples_leaf": [1, 2, 4],
    "subsample": [0.7, 0.8, 0.9, 1.0],
}

# ---------------------------------------------------------------------------
# Feature computation helpers
# ---------------------------------------------------------------------------


def _ema(closes: Sequence[float], period: int) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if period < 1 or n < period:
        return out
    k = 2.0 / (period + 1)
    avg = sum(closes[:period]) / period
    out[period - 1] = avg
    for i in range(period, n):
        avg = closes[i] * k + avg * (1 - k)
        out[i] = avg
    return out


def _obv(closes: Sequence[float], volumes: Sequence[float]) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    out[0] = 0.0
    cumulative = 0.0
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            cumulative += volumes[i]
        elif closes[i] < closes[i - 1]:
            cumulative -= volumes[i]
        out[i] = cumulative
    return out


def _vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    cum_tp_vol = 0.0
    cum_vol = 0.0
    for i in range(n):
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        cum_tp_vol += tp * volumes[i]
        cum_vol += volumes[i]
        out[i] = cum_tp_vol / cum_vol if cum_vol > 0 else None
    return out


def _bbands(
    closes: Sequence[float], period: int = 20, num_std: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Returns (upper, lower, width)."""
    n = len(closes)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    width: list[float | None] = [None] * n
    mid = sma(list(closes), period)
    for i in range(period - 1, n):
        if mid[i] is None or mid[i] == 0:
            continue
        window = closes[i - period + 1: i + 1]
        mean = mid[i]
        var = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(var)
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
        width[i] = (2.0 * num_std * std) / mean
    return upper, lower, width


def _atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float | None]:
    n = len(highs)
    out: list[float | None] = [None] * n
    if period < 1 or n <= period:
        return out
    trs: list[float] = [0.0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hc, lc))
    first_sum = sum(trs[1: period + 1])
    cur = first_sum / period
    out[period] = cur
    for i in range(period + 1, n):
        cur = (cur * (period - 1) + trs[i]) / period
        out[i] = cur
    return out


def _log_returns(closes: Sequence[float], period: int = 1) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    for i in range(period, n):
        if closes[i - period] > 0 and closes[i] > 0:
            out[i] = math.log(closes[i] / closes[i - period])
        else:
            out[i] = 0.0
    return out


def _rolling_volatility(closes: Sequence[float], period: int = 20) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if period < 2 or n <= period:
        return out
    lr = _log_returns(closes, 1)
    for i in range(period, n):
        window = [lr[j] for j in range(i - period + 1, i + 1) if lr[j] is not None]
        if len(window) < 2:
            out[i] = 0.0
            continue
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
        out[i] = math.sqrt(var)
    return out


# Canonical mapping from feature catalog name → computation
_FEATURE_BUILDERS: dict[str, Callable] = {}


def compute_all_catalog_features(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> dict[str, list[float | None]]:
    """Compute every feature in the catalog and return {name: values_list}."""
    n = len(closes)
    result: dict[str, list[float | None]] = {}

    result["rsi_14"] = rsi(closes, 14)
    result["rsi_7"] = rsi(closes, 7)
    result["sma_20"] = sma(list(closes), 20)
    result["sma_50"] = sma(list(closes), 50)
    result["ema_12"] = _ema(closes, 12)
    result["ema_26"] = _ema(closes, 26)

    ema12 = result["ema_12"]
    ema26 = result["ema_26"]
    macd_line: list[float | None] = [None] * n
    for i in range(n):
        if ema12[i] is not None and ema26[i] is not None:
            macd_line[i] = ema12[i] - ema26[i]
    result["macd"] = macd_line

    macd_vals = [v if v is not None else 0.0 for v in macd_line]
    signal = _ema(macd_vals, 9)
    result["macd_signal"] = signal

    macd_hist: list[float | None] = [None] * n
    for i in range(n):
        if macd_line[i] is not None and signal[i] is not None:
            macd_hist[i] = macd_line[i] - signal[i]
    result["macd_hist"] = macd_hist

    bb_upper, bb_lower, bb_width = _bbands(closes, 20, 2.0)
    result["bbands_upper"] = bb_upper
    result["bbands_lower"] = bb_lower
    result["bbands_width"] = bb_width

    result["atr_14"] = _atr(highs, lows, closes, 14)
    result["obv"] = _obv(closes, volumes)
    result["vwap"] = _vwap(highs, lows, closes, volumes)
    result["log_return_1"] = _log_returns(closes, 1)
    result["log_return_5"] = _log_returns(closes, 5)
    result["volatility_20"] = _rolling_volatility(closes, 20)

    return result


# ---------------------------------------------------------------------------
# Label generation
# ---------------------------------------------------------------------------


def _generate_binary_labels(
    closes: Sequence[float],
    horizon: int = 5,
) -> list[int | None]:
    """Generate binary label: 1 if price goes UP over `horizon` bars, else 0.

    Returns None for the last `horizon` bars where the future is unknown.
    """
    n = len(closes)
    labels: list[int | None] = [None] * n
    for i in range(n - horizon):
        labels[i] = 1 if closes[i + horizon] > closes[i] else 0
    return labels


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------


def _build_signal_dataset(
    candles: list[Candle],
    feature_names: list[str],
    horizon: int = 5,
) -> tuple[list[list[float]], list[int], list[datetime]]:
    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    timestamps = [c.timestamp for c in candles]

    all_features = compute_all_catalog_features(opens, highs, lows, closes, volumes)
    labels = _generate_binary_labels(closes, horizon)

    X: list[list[float]] = []
    y: list[int] = []
    ts_out: list[datetime] = []

    for i in range(len(candles)):
        if labels[i] is None:
            continue
        vals = [all_features[f][i] for f in feature_names]
        if any(v is None for v in vals):
            continue
        X.append([float(v) for v in vals])  # type: ignore[arg-type]
        y.append(labels[i])
        ts_out.append(timestamps[i])

    return X, y, ts_out


# ---------------------------------------------------------------------------
# Public training function
# ---------------------------------------------------------------------------


def _fetch_candles(
    db: Session,
    symbol_id: int,
    timeframe: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Candle]:
    q = (
        db.query(Candle)
        .filter(Candle.symbol_id == symbol_id, Candle.timeframe == timeframe)
    )
    if start:
        q = q.filter(Candle.timestamp >= start)
    if end:
        q = q.filter(Candle.timestamp <= end)
    return q.order_by(Candle.timestamp.asc()).all()


def train_signal_model(
    db: Session,
    *,
    symbol_id: int,
    timeframe: str = "1h",
    feature_names: list[str],
    start: datetime | None = None,
    end: datetime | None = None,
    horizon: int = 5,
    test_size: float = 0.2,
    random_state: int = 42,
    model_name: str = "signal_gbc",
    tune: bool = False,
    tune_n_iter: int = 30,
    tune_cv: int = 5,
    progress_cb: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """Train a binary signal model end-to-end.

    1. Fetch candles
    2. Compute features + binary labels (up/down over horizon)
    3. Train GradientBoostingClassifier (with optional tuning)
    4. Save artifact
    5. Write MLModelMetadata
    6. Return summary
    """
    def _progress(pct: int, phase: str) -> None:
        if progress_cb:
            progress_cb(pct, phase)

    _progress(5, "Fetching candles")
    candles = _fetch_candles(db, symbol_id, timeframe, start, end)
    if len(candles) < 80:
        raise ValueError(
            f"Not enough candles to train ({len(candles)}). "
            "Need at least 80 bars."
        )

    _progress(15, "Computing features and labels")
    X, y, timestamps = _build_signal_dataset(candles, feature_names, horizon)
    if len(X) < 40:
        raise ValueError(
            f"Not enough labeled samples ({len(X)}). "
            "Need at least 40 usable rows after warmup."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y,
    )

    _progress(25, "Training model" + (" with hyperparameter tuning" if tune else ""))

    tuning_info: dict[str, Any] = {}

    if tune:
        base_clf = GradientBoostingClassifier(random_state=random_state)
        cv = StratifiedKFold(n_splits=tune_cv, shuffle=True, random_state=random_state)
        search = RandomizedSearchCV(
            base_clf,
            param_distributions=DEFAULT_SIGNAL_PARAM_GRID,
            n_iter=tune_n_iter,
            cv=cv,
            scoring="f1",
            random_state=random_state,
            n_jobs=-1,
            refit=True,
        )
        search.fit(X_train, y_train)
        clf = search.best_estimator_

        serializable_params = {
            k: (int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
            for k, v in search.best_params_.items()
        }
        tuning_info = {
            "tuned": True,
            "best_params": serializable_params,
            "cv_best_score": round(float(search.best_score_), 4),
            "cv_folds": tune_cv,
            "n_iter": tune_n_iter,
        }
    else:
        clf = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.1,
            random_state=random_state,
        )
        clf.fit(X_train, y_train)
        tuning_info = {
            "tuned": False,
            "best_params": {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.1},
        }

    _progress(80, "Evaluating model")
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    _progress(90, "Saving model artifact")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "_tuned" if tune else ""
    filename = f"{model_name}{suffix}_{symbol_id}_{timeframe}_{ts_tag}.joblib"
    artifact_path = str(ARTIFACT_DIR / filename)
    joblib.dump({
        "model": clf,
        "feature_keys": feature_names,
        "model_type": "signal",
        "horizon": horizon,
    }, artifact_path)

    training_start = timestamps[0] if timestamps else None
    training_end = timestamps[-1] if timestamps else None

    meta = MLModelMetadata(
        name=model_name,
        symbol_id=symbol_id,
        timeframe=timeframe,
        training_start=training_start,
        training_end=training_end,
        artifact_path=artifact_path,
        metrics={
            "accuracy": round(acc, 4),
            "n_train": len(y_train),
            "n_test": len(y_test),
            "classification_report": {
                k: ({rk: round(float(rv), 4) if isinstance(rv, float) else rv for rk, rv in v.items()} if isinstance(v, dict) else round(float(v), 4) if isinstance(v, float) else v)
                for k, v in report.items()
            },
            "model_type": "signal",
            "horizon": horizon,
            "features": feature_names,
            **tuning_info,
        },
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)

    label_dist = {str(k): y.count(k) for k in set(y)}

    _progress(100, "Complete")

    return {
        "model_id": meta.id,
        "artifact_path": artifact_path,
        "accuracy": round(acc, 4),
        "n_train": len(y_train),
        "n_test": len(y_test),
        "label_distribution": label_dist,
        "horizon": horizon,
        "features": feature_names,
        **tuning_info,
    }
