"""
CLI script to train the regime classification model (Phase 9.2 + 9.6 tuning).

Usage inside the backend container:
    python -m app.scripts.train_regime_model --symbol-id 1 --timeframe 1h

With hyperparameter tuning (Phase 9.6):
    python -m app.scripts.train_regime_model \
        --symbol-id 1 --timeframe 1h --tune \
        --tune-n-iter 30 --tune-cv 5

With date filters:
    python -m app.scripts.train_regime_model \
        --symbol-id 1 --timeframe 1h \
        --start 2026-01-01T00:00:00Z --end 2026-03-01T00:00:00Z
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


def _parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 datetime string with or without trailing 'Z'."""
    cleaned = value.rstrip("Z")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main() -> None:
    parser = argparse.ArgumentParser(description="Train regime classification model")
    parser.add_argument("--symbol-id", type=int, required=True, help="Symbol ID to train on")
    parser.add_argument("--timeframe", type=str, default="1h", help="Candle timeframe (default: 1h)")
    parser.add_argument("--start", type=str, default=None, help="Training start (ISO-8601)")
    parser.add_argument("--end", type=str, default=None, help="Training end (ISO-8601)")
    parser.add_argument("--label-window", type=int, default=20, help="Forward-looking label window")
    parser.add_argument("--trend-threshold", type=float, default=0.03, help="Trend threshold")
    parser.add_argument("--vol-threshold-pct", type=float, default=75.0, help="Volatility percentile threshold")
    parser.add_argument("--n-estimators", type=int, default=200, help="Number of trees (no-tune mode)")
    parser.add_argument("--max-depth", type=int, default=12, help="Max tree depth, 0=unlimited (no-tune mode)")
    parser.add_argument("--model-name", type=str, default="regime_rf", help="Model name prefix")
    parser.add_argument("--tune", action="store_true", help="Enable hyperparameter tuning (Phase 9.6)")
    parser.add_argument("--tune-n-iter", type=int, default=30, help="Number of random search iterations")
    parser.add_argument("--tune-cv", type=int, default=5, help="Number of CV folds")
    args = parser.parse_args()

    from app.db.session import SessionLocal
    from app.services.ml.training import train_regime_model

    start_dt = _parse_dt(args.start) if args.start else None
    end_dt = _parse_dt(args.end) if args.end else None
    max_depth = args.max_depth if args.max_depth > 0 else None

    db = SessionLocal()
    try:
        mode_str = "with hyperparameter tuning" if args.tune else "with fixed params"
        print(f"Training regime model for symbol_id={args.symbol_id}, "
              f"timeframe={args.timeframe} ({mode_str}) ...")

        result = train_regime_model(
            db,
            symbol_id=args.symbol_id,
            timeframe=args.timeframe,
            start=start_dt,
            end=end_dt,
            label_window=args.label_window,
            trend_threshold=args.trend_threshold,
            vol_threshold_pct=args.vol_threshold_pct,
            n_estimators=args.n_estimators,
            max_depth=max_depth,
            model_name=args.model_name,
            tune=args.tune,
            tune_n_iter=args.tune_n_iter,
            tune_cv=args.tune_cv,
        )

        print("\n=== Training Complete ===")
        print(f"Model ID    : {result['model_id']}")
        print(f"Artifact    : {result['artifact_path']}")
        print(f"Accuracy    : {result['accuracy']:.4f}")
        print(f"Train size  : {result['n_train']}")
        print(f"Test size   : {result['n_test']}")
        print(f"Label dist  : {json.dumps(result['label_distribution'])}")

        if result.get("tuned"):
            print(f"\n--- Tuning Results ---")
            print(f"CV folds    : {result.get('cv_folds')}")
            print(f"Iterations  : {result.get('n_iter')}")
            print(f"CV score    : {result.get('cv_best_score', 0):.4f} (f1_weighted)")
            print(f"Best params : {json.dumps(result.get('best_params', {}), indent=2)}")
        else:
            print(f"\nParams      : {json.dumps(result.get('best_params', {}))}")

        print("\nClassification report:")
        report = result["classification_report"]
        for cls_name in sorted(set(report.keys()) - {"accuracy", "macro avg", "weighted avg"}):
            cls_data = report[cls_name]
            print(f"  {cls_name:12s}  precision={cls_data['precision']:.3f}  "
                  f"recall={cls_data['recall']:.3f}  f1={cls_data['f1-score']:.3f}  "
                  f"support={cls_data['support']}")
        print(f"\n  {'accuracy':12s}  {report['accuracy']:.3f}")
        w = report.get("weighted avg", {})
        print(f"  {'weighted avg':12s}  precision={w.get('precision', 0):.3f}  "
              f"recall={w.get('recall', 0):.3f}  f1={w.get('f1-score', 0):.3f}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
