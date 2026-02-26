"""Market data provider abstraction and Binance implementation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

# Internal symbol (e.g. BTCUSD) -> Binance symbol
SYMBOL_TO_EXCHANGE: dict[str, str] = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
}
SUPPORTED_TIMEFRAMES = ("1h", "4h")
BINANCE_BASE_URL = "https://api.binance.com"
KLINES_LIMIT = 1000


@dataclass
class NormalizedCandle:
    """Single OHLCV candle, timezone-aware UTC."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataProvider(ABC):
    """Abstract interface for fetching historical OHLCV candles."""

    @abstractmethod
    def fetch_klines(
        self,
        exchange_symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> list[NormalizedCandle]:
        """Fetch candles for the given symbol and time range. Times in milliseconds since epoch."""
        ...


class BinanceMarketDataProvider(MarketDataProvider):
    """Binance spot klines API. No API key required for public klines."""

    def __init__(self, base_url: str = BINANCE_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_klines(
        self,
        exchange_symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> list[NormalizedCandle]:
        url = f"{self.base_url}/api/v3/klines"
        params: dict[str, Any] = {
            "symbol": exchange_symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": KLINES_LIMIT,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        return self._normalize(data)

    @staticmethod
    def _normalize(raw: list[list[Any]]) -> list[NormalizedCandle]:
        out: list[NormalizedCandle] = []
        for row in raw:
            if len(row) < 6:
                continue
            open_ts_ms = int(row[0])
            # Use open time as candle timestamp (start of period), UTC
            ts = datetime.utcfromtimestamp(open_ts_ms / 1000.0)
            # Make timezone-aware UTC for SQLAlchemy
            ts = ts.replace(tzinfo=timezone.utc)
            out.append(
                NormalizedCandle(
                    timestamp=ts,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return out


def get_exchange_symbol(internal_symbol: str) -> str:
    """Map internal symbol (e.g. BTCUSD) to exchange symbol (e.g. BTCUSDT)."""
    s = SYMBOL_TO_EXCHANGE.get(internal_symbol.upper())
    if not s:
        raise ValueError(f"Unsupported symbol for market data: {internal_symbol}")
    return s
