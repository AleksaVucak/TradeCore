"""
Training pipeline for ML regime classifier (Phase 9.2).

Fetches OHLCV candles from the database, computes feature matrix, generates
heuristic regime labels, trains a Random Forest classifier, persists the
model artifact to disk, and writes an MLModelMetadata row.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sqlalchemy.orm import Session

from app.models.candle import Candle
from app.models.ml_model_metadata import MLModelMetadata
from app.services.ml.features import FeatureRow, compute_feature_matrix
from app.services.ml.labeling import label_regimes

ARTIFACT_DIR = Path(os.environ.get("ML_ARTIFACT_DIR", "/app/ml_artifacts"))

FEATURE_KEYS: list[str] = [
    "log_return",
    "rolling_return_20",
    "volatility_20",
    "atr_14",
    "momentum_10",
    "rsi_14",
    "sma_20",
    "volume_ratio_20",
    "bb_width_20",
]


def _fetch_candles(
    db: Session,
    symbol_id: int,
    timeframe: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Candle]:
    """Fetch candles ordered by timestamp."""
    q = (
        db.query(Candle)
        .filter(Candle.symbol_id == symbol_id, Candle.timeframe == timeframe)
    )
    if start:
        q = q.filter(Candle.timestamp >= start)
    if end:
        q = q.filter(Candle.timestamp <= end)
    return q.order_by(Candle.timestamp.asc()).all()


def _build_dataset(
    candles: list[Candle],
    label_window: int = 20,
    trend_threshold: float = 0.03,
    vol_threshold_pct: float = 75.0,
) -> tuple[list[list[float]], list[str], list[datetime]]:
    """
    Build X (feature matrix), y (labels), and corresponding timestamps from
    raw candles.  Rows with any None feature or None label are excluded.

    Returns:
        (X, y, timestamps) where X is a 2D list of floats, y is a list of
        regime strings, and timestamps tracks the bar time for each row.
    """
    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    timestamps = [c.timestamp for c in candles]

    features: list[FeatureRow] = compute_feature_matrix(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )
    labels = label_regimes(
        closes,
        window=label_window,
        trend_threshold=trend_threshold,
        vol_threshold_pct=vol_threshold_pct,
    )

    X: list[list[float]] = []
    y: list[str] = []
    ts_out: list[datetime] = []

    for i, (row, lbl) in enumerate(zip(features, labels)):
        if lbl is None:
            continue
        vals = [row.get(k) for k in FEATURE_KEYS]
        if any(v is None for v in vals):
            continue
        X.append([float(v) for v in vals])  # type: ignore[arg-type]
        y.append(lbl)
        ts_out.append(timestamps[i])

    return X, y, ts_out


def train_regime_model(
    db: Session,
    *,
    symbol_id: int,
    timeframe: str = "1h",
    start: datetime | None = None,
    end: datetime | None = None,
    label_window: int = 20,
    trend_threshold: float = 0.03,
    vol_threshold_pct: float = 75.0,
    test_size: float = 0.2,
    random_state: int = 42,
    n_estimators: int = 200,
    max_depth: int | None = 12,
    model_name: str = "regime_rf",
) -> dict[str, Any]:
    """
    End-to-end training pipeline.

    1. Fetches candles from DB
    2. Computes features + heuristic labels
    3. Trains RandomForestClassifier
    4. Saves model artifact to disk
    5. Writes MLModelMetadata row
    6. Returns summary dict with metrics and metadata id

    Args:
        db: SQLAlchemy session.
        symbol_id: symbol to train on.
        timeframe: candle timeframe (e.g. "1h").
        start / end: optional date filters.
        label_window: forward-looking window for label heuristic.
        trend_threshold: threshold for labeling "trend".
        vol_threshold_pct: percentile threshold for "high_vol".
        test_size: fraction held out for evaluation.
        random_state: seed for reproducibility.
        n_estimators: number of trees in the forest.
        max_depth: max tree depth (None = unlimited).
        model_name: name prefix for the artifact file and DB row.

    Returns:
        Dict with keys: model_id, artifact_path, accuracy, classification_report,
        n_train, n_test, label_distribution.
    """
    candles = _fetch_candles(db, symbol_id, timeframe, start, end)
    if len(candles) < 60:
        raise ValueError(
            f"Not enough candles to train ({len(candles)}). "
            "Need at least 60 bars after filtering."
        )

    X, y, timestamps = _build_dataset(
        candles,
        label_window=label_window,
        trend_threshold=trend_threshold,
        vol_threshold_pct=vol_threshold_pct,
    )
    if len(X) < 30:
        raise ValueError(
            f"Not enough labeled samples ({len(X)}). "
            "Need at least 30 usable rows after warmup."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
        class_weight="balanced",
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{model_name}_{symbol_id}_{timeframe}_{ts_tag}.joblib"
    artifact_path = str(ARTIFACT_DIR / filename)
    joblib.dump({"model": clf, "feature_keys": FEATURE_KEYS}, artifact_path)

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
            "classification_report": report,
        },
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)

    label_dist = {}
    for lbl in y:
        label_dist[lbl] = label_dist.get(lbl, 0) + 1

    return {
        "model_id": meta.id,
        "artifact_path": artifact_path,
        "accuracy": round(acc, 4),
        "classification_report": report,
        "n_train": len(y_train),
        "n_test": len(y_test),
        "label_distribution": label_dist,
    }


def load_model(artifact_path: str) -> tuple[RandomForestClassifier, list[str]]:
    """
    Load a persisted model artifact.

    Returns (classifier, feature_keys).
    """
    data = joblib.load(artifact_path)
    return data["model"], data["feature_keys"]
