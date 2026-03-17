"""Idempotent candle ingestion: fetch from provider and upsert into candles table."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.candle import Candle
from app.models.symbol import Symbol
from app.services.market_data.provider import (
    BinanceMarketDataProvider,
    SUPPORTED_TIMEFRAMES,
    get_exchange_symbol,
)

if TYPE_CHECKING:
    from app.services.market_data.provider import MarketDataProvider

logger = get_logger(__name__)


def ingest_candles(
    db: Session,
    symbol_id: int,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    *,
    provider: "MarketDataProvider | None" = None,
) -> int:
    """
    Fetch OHLCV from provider and upsert into candles. Idempotent.
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

    total_upserted = 0
    current_start = start_ms

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

        last_ts = chunk[-1].timestamp
        current_start = int(last_ts.timestamp() * 1000) + 1
        if len(chunk) < 1000:
            break

    db.commit()
    logger.info(
        "candles_ingested",
        symbol_id=symbol_id,
        timeframe=timeframe,
        total_upserted=total_upserted,
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
