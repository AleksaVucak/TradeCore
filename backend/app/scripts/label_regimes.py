"""
CLI script to run batch regime inference and persist labels (Phase 9.3).

Usage inside the backend container:
    python -m app.scripts.label_regimes --symbol-id 1 --timeframe 1h

With date filters:
    python -m app.scripts.label_regimes \
        --symbol-id 1 --timeframe 1h \
        --start 2026-01-01T00:00:00Z --end 2026-03-01T00:00:00Z

With a specific model:
    python -m app.scripts.label_regimes --symbol-id 1 --timeframe 1h --model-id 1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


def _parse_dt(value: str) -> datetime:
    cleaned = value.rstrip("Z")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main() -> None:
    parser = argparse.ArgumentParser(description="Run batch regime labeling")
    parser.add_argument("--symbol-id", type=int, required=True, help="Symbol ID")
    parser.add_argument("--timeframe", type=str, default="1h", help="Candle timeframe (default: 1h)")
    parser.add_argument("--start", type=str, default=None, help="Start time (ISO-8601)")
    parser.add_argument("--end", type=str, default=None, help="End time (ISO-8601)")
    parser.add_argument("--model-id", type=int, default=None, help="Specific model ID (optional)")
    parser.add_argument("--backtest-run-id", type=str, default=None, help="Backtest run ID to link (optional)")
    args = parser.parse_args()

    from app.db.session import SessionLocal
    from app.services.ml.inference import label_candles

    start_dt = _parse_dt(args.start) if args.start else None
    end_dt = _parse_dt(args.end) if args.end else None

    db = SessionLocal()
    try:
        print(f"Labeling regimes for symbol_id={args.symbol_id}, "
              f"timeframe={args.timeframe} ...")
        result = label_candles(
            db,
            symbol_id=args.symbol_id,
            timeframe=args.timeframe,
            start=start_dt,
            end=end_dt,
            model_id=args.model_id,
            backtest_run_id=args.backtest_run_id,
        )
        print("\n=== Labeling Complete ===")
        print(f"Model ID       : {result['model_id']}")
        print(f"Artifact       : {result['artifact_path']}")
        print(f"Total candles  : {result['total_candles']}")
        print(f"Labeled bars   : {result['labeled_bars']}")
        print(f"Skipped (warmup): {result['skipped_bars']}")
        print(f"Distribution   : {json.dumps(result['regime_distribution'])}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
