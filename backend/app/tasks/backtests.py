"""Celery tasks for running backtests (Phase 6.3)."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.candle import Candle
from app.models.strategy import Strategy, StrategyVersion
from app.schemas.strategy_config import validate_strategy_config
from app.services.backtest import (
  BacktestCandle,
  compute_metrics_from_result,
  run_backtest_rsi_ma,
)

logger = logging.getLogger(__name__)


def _parse_iso8601(dt_str: str) -> datetime:
  """Parse ISO8601 string into timezone-aware UTC datetime."""
  dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
  if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
  return dt


def _timeframe_to_hours(timeframe: str) -> float:
  mapping: dict[str, float] = {
    "1h": 1.0,
    "4h": 4.0,
  }
  return mapping.get(timeframe, 1.0)


@celery_app.task
def run_backtest_task(
  *,
  strategy_version_id: int,
  symbol_id: int,
  timeframe: str,
  start_time: str,
  end_time: str,
  initial_equity: float = 10_000.0,
) -> dict[str, Any]:
  """Async backtest task.

  Loads candles and strategy config from the database, runs the RSI+MA backtest
  engine and metrics module, and returns a JSON-serializable summary.

  Dates are ISO8601 strings (e.g. 2025-01-01T00:00:00Z).
  """
  db = SessionLocal()
  try:
    start_dt = _parse_iso8601(start_time)
    end_dt = _parse_iso8601(end_time)
    if start_dt >= end_dt:
      raise ValueError("start_time must be before end_time")

    # Load strategy version and associated strategy to get type and config.
    strategy_version = (
      db.query(StrategyVersion)
      .options(joinedload(StrategyVersion.strategy))
      .filter(StrategyVersion.id == strategy_version_id)
      .first()
    )
    if strategy_version is None:
      raise ValueError(f"StrategyVersion id {strategy_version_id} not found")
    strategy: Strategy = strategy_version.strategy

    # Validate config for this strategy type.
    validated_config = validate_strategy_config(strategy.strategy_type, strategy_version.config)

    # Load candles for symbol / timeframe / time range.
    candles_db = (
      db.query(Candle)
      .filter(
        Candle.symbol_id == symbol_id,
        Candle.timeframe == timeframe,
        Candle.timestamp >= start_dt,
        Candle.timestamp <= end_dt,
      )
      .order_by(Candle.timestamp.asc())
      .all()
    )
    if not candles_db:
      logger.warning(
        "No candles found for backtest: symbol_id=%s timeframe=%s start=%s end=%s",
        symbol_id,
        timeframe,
        start_dt,
        end_dt,
      )

    candles_bt = [
      BacktestCandle.from_candle_like(
        timestamp=c.timestamp,
        open=c.open,
        high=c.high,
        low=c.low,
        close=c.close,
        volume=c.volume,
      )
      for c in candles_db
    ]

    logger.info(
      "Running backtest: strategy_version_id=%s symbol_id=%s timeframe=%s candles=%s",
      strategy_version_id,
      symbol_id,
      timeframe,
      len(candles_bt),
    )

    bt_result = run_backtest_rsi_ma(candles_bt, validated_config, initial_equity=initial_equity)
    period_hours = _timeframe_to_hours(timeframe)
    metrics = compute_metrics_from_result(bt_result, period_hours=period_hours)

    summary: dict[str, Any] = {
      "strategy_id": strategy.id,
      "strategy_version_id": strategy_version.id,
      "symbol_id": symbol_id,
      "timeframe": timeframe,
      "start_time": start_dt.isoformat(),
      "end_time": end_dt.isoformat(),
      "initial_equity": bt_result.initial_equity,
      "final_equity": bt_result.final_equity,
      "num_candles": len(candles_bt),
      "num_trades": int(metrics.get("num_trades", 0)),
    }

    logger.info(
      "Backtest completed: strategy_version_id=%s symbol_id=%s timeframe=%s final_equity=%s",
      strategy_version_id,
      symbol_id,
      timeframe,
      bt_result.final_equity,
    )

    return {
      "status": "ok",
      "summary": summary,
      "metrics": metrics,
    }
  except Exception as exc:  # pragma: no cover - error path
    logger.exception(
      "Backtest failed: strategy_version_id=%s symbol_id=%s timeframe=%s error=%s",
      strategy_version_id,
      symbol_id,
      timeframe,
      exc,
    )
    # Re-raise so Celery marks task as failed.
    raise
  finally:
    db.close()

