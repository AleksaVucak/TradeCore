"""News headline fetcher using NewsAPI (Phase 17.1 + 17.5).

Fetches recent English-language news articles for a given query term
(typically a crypto symbol like "Bitcoin" or "Ethereum") and returns
a list of structured article dicts ready for sentiment scoring.

Phase 17.5 improvements:
- Structured ``FetchOutcome`` return type so callers know *why* a fetch
  returned zero articles (missing key, invalid key, rate-limited, network
  error, or genuinely no articles).
- Expanded ``SYMBOL_QUERY_MAP`` covering common crypto pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"

SYMBOL_QUERY_MAP: dict[str, str] = {
    "BTCUSDT": "Bitcoin OR BTC",
    "BTCUSD": "Bitcoin OR BTC",
    "ETHUSDT": "Ethereum OR ETH",
    "ETHUSD": "Ethereum OR ETH",
    "SOLUSDT": "Solana OR SOL crypto",
    "SOLUSD": "Solana OR SOL crypto",
    "XRPUSDT": "Ripple OR XRP",
    "XRPUSD": "Ripple OR XRP",
    "ADAUSDT": "Cardano OR ADA crypto",
    "ADAUSD": "Cardano OR ADA crypto",
    "DOGEUSDT": "Dogecoin OR DOGE",
    "DOGEUSD": "Dogecoin OR DOGE",
    "BNBUSDT": "Binance Coin OR BNB crypto",
    "BNBUSD": "Binance Coin OR BNB crypto",
}

DEFAULT_PAGE_SIZE = 50


class FetchStatus(str, Enum):
    """Machine-readable reason code for a fetch attempt."""

    OK = "ok"
    NO_API_KEY = "no_api_key"
    INVALID_API_KEY = "invalid_api_key"
    RATE_LIMITED = "rate_limited"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    NO_ARTICLES = "no_articles"


@dataclass(frozen=True, slots=True)
class NewsArticle:
    title: str
    url: str
    source: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class FetchOutcome:
    """Result of a single fetch_news call — carries articles *and* a status."""

    status: FetchStatus
    articles: list[NewsArticle] = field(default_factory=list)
    detail: str = ""


def _parse_published(raw: str | None) -> datetime:
    """Parse ISO-8601 timestamp from NewsAPI, falling back to now()."""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def fetch_news(
    symbol: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[NewsArticle]:
    """Fetch recent news headlines for a symbol from NewsAPI.

    Thin wrapper kept for backward compatibility with existing callers that
    only care about the article list. Internally delegates to
    :func:`fetch_news_with_status`.
    """
    outcome = fetch_news_with_status(
        symbol, page_size=page_size, from_date=from_date, to_date=to_date
    )
    return outcome.articles


def fetch_news_with_status(
    symbol: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    from_date: str | None = None,
    to_date: str | None = None,
) -> FetchOutcome:
    """Fetch news and return a :class:`FetchOutcome` with a machine-readable status.

    This is the preferred entry point from Phase 17.5 onward because callers
    can inspect ``outcome.status`` and ``outcome.detail`` for diagnostics.
    """
    api_key = settings.newsapi_key
    if not api_key:
        logger.warning(
            "newsapi_key_not_set",
            hint="Set NEWSAPI_KEY in .env to enable news fetching",
        )
        return FetchOutcome(
            status=FetchStatus.NO_API_KEY,
            detail="NEWSAPI_KEY is not configured. Set it in your project root .env file.",
        )

    query = SYMBOL_QUERY_MAP.get(symbol.upper(), symbol)

    params: dict[str, str | int] = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(page_size, 100),
        "apiKey": api_key,
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    try:
        resp = httpx.get(NEWSAPI_EVERYTHING_URL, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        body = exc.response.text[:500]

        if code == 401:
            logger.error("newsapi_invalid_key", status_code=code, body=body)
            return FetchOutcome(
                status=FetchStatus.INVALID_API_KEY,
                detail="NewsAPI rejected the API key (HTTP 401). Verify NEWSAPI_KEY in .env.",
            )
        if code == 429:
            logger.warning("newsapi_rate_limited", status_code=code, body=body)
            return FetchOutcome(
                status=FetchStatus.RATE_LIMITED,
                detail="NewsAPI rate limit reached (HTTP 429). Free tier allows 100 requests/day.",
            )

        logger.error("newsapi_http_error", status_code=code, body=body)
        return FetchOutcome(
            status=FetchStatus.HTTP_ERROR,
            detail=f"NewsAPI returned HTTP {code}.",
        )
    except httpx.RequestError as exc:
        logger.error("newsapi_request_error", error=str(exc))
        return FetchOutcome(
            status=FetchStatus.NETWORK_ERROR,
            detail=f"Network error contacting NewsAPI: {exc}",
        )

    articles_raw = data.get("articles") or []
    articles: list[NewsArticle] = []
    for art in articles_raw:
        title = (art.get("title") or "").strip()
        if not title or title == "[Removed]":
            continue
        articles.append(
            NewsArticle(
                title=title,
                url=art.get("url") or "",
                source=(art.get("source") or {}).get("name", "unknown"),
                published_at=_parse_published(art.get("publishedAt")),
            )
        )

    if not articles:
        logger.info(
            "newsapi_no_articles_returned",
            symbol=symbol,
            query=query,
        )
        return FetchOutcome(
            status=FetchStatus.NO_ARTICLES,
            detail=f"NewsAPI returned no articles for query '{query}'. Try a different symbol or check your date range.",
        )

    return FetchOutcome(status=FetchStatus.OK, articles=articles)
