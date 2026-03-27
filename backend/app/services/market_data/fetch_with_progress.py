"""Candle ingestion with progress tracking for FetchJob (Phase 13.1)."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.candle import Candle
from app.models.fetch_job import FetchJob
from app.models.symbol import Symbol
from app.services.market_data.provider import (
    BinanceMarketDataProvider,
    SUPPORTED_TIMEFRAMES,
    get_exchange_symbol,
)

if TYPE_CHECKING:
    from app.services.market_data.provider import MarketDataProvider

logger = get_logger(__name__)

CHUNK_SIZE_MS = {
    "1h": 1000 * 3600 * 1000,
    "4h": 1000 * 4 * 3600 * 1000,
}


def _estimate_total_chunks(
    start_ms: int,
    end_ms: int,
    timeframe: str,
) -> int:
    """Estimate the number of chunks we'll need to fetch."""
    range_ms = end_ms - start_ms
    if range_ms <= 0:
        return 0
    chunk_ms = CHUNK_SIZE_MS.get(timeframe, 1000 * 3600 * 1000)
    return max(1, (range_ms + chunk_ms - 1) // chunk_ms)


def ingest_candles_with_progress(
    db: Session,
    job: FetchJob,
    symbol_id: int,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    *,
    provider: "MarketDataProvider | None" = None,
) -> int:
    """
    Fetch OHLCV from provider and upsert into candles, updating FetchJob progress.
    Returns total number of candles upserted.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Use one of {SUPPORTED_TIMEFRAMES}")

    symbol = db.get(Symbol, symbol_id)
    if not symbol:
        raise ValueError(f"Symbol id {symbol_id} not found")
    exchange_symbol = get_exchange_symbol(symbol.symbol)

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)
    if start_ms >= end_ms:
        raise ValueError("start_date must be before end_date")

    if provider is None:
        provider = BinanceMarketDataProvider()

    total_chunks = _estimate_total_chunks(start_ms, end_ms, timeframe)
    job.total_chunks = total_chunks
    job.completed_chunks = 0
    job.candles_fetched = 0
    job.progress_pct = 0.0
    db.commit()

    total_upserted = 0
    current_start = start_ms
    chunks_done = 0

    while current_start < end_ms:
        chunk = provider.fetch_klines(exchange_symbol, timeframe, current_start, end_ms)
        if not chunk:
            break

        rows = [
            {
                "symbol_id": symbol_id,
                "timeframe": timeframe,
                "timestamp": c.timestamp,
                "open": _validate_price(c.open),
                "high": _validate_price(c.high),
                "low": _validate_price(c.low),
                "close": _validate_price(c.close),
                "volume": _validate_volume(c.volume),
            }
            for c in chunk
        ]

        ins = pg_insert(Candle).values(rows)
        stmt = ins.on_conflict_do_update(
            index_elements=["symbol_id", "timeframe", "timestamp"],
            set_={
                Candle.open: ins.excluded.open,
                Candle.high: ins.excluded.high,
                Candle.low: ins.excluded.low,
                Candle.close: ins.excluded.close,
                Candle.volume: ins.excluded.volume,
            },
        )
        db.execute(stmt)
        total_upserted += len(rows)
        chunks_done += 1

        job.completed_chunks = chunks_done
        job.candles_fetched = total_upserted
        job.progress_pct = min(100.0, (chunks_done / max(1, total_chunks)) * 100)
        db.commit()

        last_ts = chunk[-1].timestamp
        current_start = int(last_ts.timestamp() * 1000) + 1
        if len(chunk) < 1000:
            break

    logger.info(
        "candles_ingested_with_progress",
        symbol_id=symbol_id,
        timeframe=timeframe,
        total_upserted=total_upserted,
        chunks_completed=chunks_done,
    )
    return total_upserted


def _validate_price(v: float) -> float:
    if v < 0 or not isinstance(v, (int, float)):
        raise ValueError(f"Invalid OHLC price: {v}")
    return float(v)


def _validate_volume(v: float) -> float:
    if v < 0 or not isinstance(v, (int, float)):
        raise ValueError(f"Invalid volume: {v}")
    return float(v)
