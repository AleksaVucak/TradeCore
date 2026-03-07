"""
Regime inference service (Phase 9.3).

Loads a trained regime model, computes features from candles, runs predictions,
and persists RegimeLabel rows to the database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import and_, delete
from sqlalchemy.orm import Session

from app.models.candle import Candle
from app.models.ml_model_metadata import MLModelMetadata
from app.models.regime_label import RegimeLabel
from app.services.ml.features import FeatureRow, compute_feature_matrix
from app.services.ml.training import FEATURE_KEYS, load_model


def get_latest_model(
    db: Session,
    symbol_id: int,
    timeframe: str,
) -> MLModelMetadata | None:
    """Return the most recently created model for a given symbol + timeframe."""
    return (
        db.query(MLModelMetadata)
        .filter(
            MLModelMetadata.symbol_id == symbol_id,
            MLModelMetadata.timeframe == timeframe,
        )
        .order_by(MLModelMetadata.created_at.desc())
        .first()
    )


def predict_regimes(
    *,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    artifact_path: str,
) -> list[str | None]:
    """
    Compute features and run the trained classifier to predict a regime label
    per bar.

    Returns a list aligned with the input (same length). Bars where any feature
    is None (warmup period) get None; the rest get a regime string.
    """
    n = len(closes)
    if n == 0:
        return []

    clf, feature_keys = load_model(artifact_path)

    features: list[FeatureRow] = compute_feature_matrix(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )

    predictions: list[str | None] = [None] * n
    usable_indices: list[int] = []
    X: list[list[float]] = []

    for i, row in enumerate(features):
        vals = [row.get(k) for k in feature_keys]
        if any(v is None for v in vals):
            continue
        usable_indices.append(i)
        X.append([float(v) for v in vals])  # type: ignore[arg-type]

    if X:
        preds = clf.predict(X)
        for idx, pred in zip(usable_indices, preds):
            predictions[idx] = pred

    return predictions


def label_candles(
    db: Session,
    *,
    symbol_id: int,
    timeframe: str,
    start: datetime | None = None,
    end: datetime | None = None,
    model_id: int | None = None,
    backtest_run_id: str | None = None,
) -> dict:
    """
    End-to-end regime labeling: fetch candles, predict, persist RegimeLabel rows.

    If model_id is not provided, the latest model for the symbol+timeframe is
    used. Existing labels for the same model + symbol + timeframe + date range
    are deleted first (idempotent).

    Returns a summary dict with counts.
    """
    if model_id is not None:
        meta = db.query(MLModelMetadata).filter(MLModelMetadata.id == model_id).first()
    else:
        meta = get_latest_model(db, symbol_id, timeframe)

    if meta is None:
        raise ValueError(
            f"No trained model found for symbol_id={symbol_id}, "
            f"timeframe={timeframe}. Train a model first (Phase 9.2)."
        )

    q = (
        db.query(Candle)
        .filter(Candle.symbol_id == symbol_id, Candle.timeframe == timeframe)
    )
    if start:
        q = q.filter(Candle.timestamp >= start)
    if end:
        q = q.filter(Candle.timestamp <= end)
    candles = q.order_by(Candle.timestamp.asc()).all()

    if len(candles) < 25:
        raise ValueError(
            f"Not enough candles ({len(candles)}) for regime inference. "
            "Need at least 25 bars to compute features."
        )

    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    timestamps = [c.timestamp for c in candles]

    predictions = predict_regimes(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
        artifact_path=meta.artifact_path,
    )

    del_conditions = [
        RegimeLabel.model_id == meta.id,
        RegimeLabel.symbol_id == symbol_id,
        RegimeLabel.timeframe == timeframe,
    ]
    if start:
        del_conditions.append(RegimeLabel.timestamp >= start)
    if end:
        del_conditions.append(RegimeLabel.timestamp <= end)
    db.execute(delete(RegimeLabel).where(and_(*del_conditions)))

    labels_to_add: list[RegimeLabel] = []
    regime_counts: dict[str, int] = {}

    for i, pred in enumerate(predictions):
        if pred is None:
            continue
        labels_to_add.append(
            RegimeLabel(
                model_id=meta.id,
                backtest_run_id=backtest_run_id,
                symbol_id=symbol_id,
                timeframe=timeframe,
                timestamp=timestamps[i],
                regime=pred,
            )
        )
        regime_counts[pred] = regime_counts.get(pred, 0) + 1

    db.add_all(labels_to_add)
    db.commit()

    return {
        "model_id": meta.id,
        "artifact_path": meta.artifact_path,
        "symbol_id": symbol_id,
        "timeframe": timeframe,
        "total_candles": len(candles),
        "labeled_bars": len(labels_to_add),
        "skipped_bars": len(candles) - len(labels_to_add),
        "regime_distribution": regime_counts,
    }
