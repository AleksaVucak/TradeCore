"""News headline fetcher using NewsAPI (Phase 17.1 + 17.5 + 17.6).

Fetches recent English-language news articles for a given query term
(typically a crypto symbol like "Bitcoin" or "Ethereum") and returns
a list of structured article dicts ready for sentiment scoring.

Phase 17.6 improvements:
- ``build_query_for_symbol`` auto-derives a search query for *any* symbol
  by stripping common quote suffixes (USDT, USD, BUSD, EUR) and looking up
  the base asset in ``BASE_ASSET_QUERY_MAP``.  Unknown assets fall back to
  ``"<base> crypto"`` which still yields reasonable results.
- Post-fetch noise filter removes articles whose title is pure promotional
  spam, very short, or consists only of tickers / numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"

# ---------------------------------------------------------------------------
# Phase 17.6 — base-asset → search query mapping
# ---------------------------------------------------------------------------

BASE_ASSET_QUERY_MAP: dict[str, str] = {
    "BTC": "Bitcoin OR BTC",
    "ETH": "Ethereum OR ETH",
    "SOL": "Solana OR SOL crypto",
    "XRP": "Ripple OR XRP",
    "ADA": "Cardano OR ADA crypto",
    "DOGE": "Dogecoin OR DOGE",
    "BNB": "Binance Coin OR BNB crypto",
    "DOT": "Polkadot OR DOT crypto",
    "AVAX": "Avalanche OR AVAX crypto",
    "MATIC": "Polygon OR MATIC crypto",
    "POL": "Polygon OR POL crypto",
    "LINK": "Chainlink OR LINK crypto",
    "LTC": "Litecoin OR LTC",
    "UNI": "Uniswap OR UNI crypto",
    "ATOM": "Cosmos OR ATOM crypto",
    "NEAR": "NEAR Protocol crypto",
    "APT": "Aptos OR APT crypto",
    "ARB": "Arbitrum OR ARB crypto",
    "OP": "Optimism OR OP crypto",
    "SUI": "SUI crypto blockchain",
    "FIL": "Filecoin OR FIL crypto",
    "SHIB": "Shiba Inu OR SHIB",
    "PEPE": "PEPE memecoin crypto",
    "TRX": "TRON OR TRX crypto",
}

_QUOTE_SUFFIXES = ("USDT", "BUSD", "USDC", "USD", "EUR", "GBP", "BTC", "ETH")

_NOISE_RE = re.compile(
    r"^[\d\s\W]+$"
    r"|^.{0,15}$"
    r"|sponsored|presale hits|buy now|limited offer|act fast",
    re.IGNORECASE,
)

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


def _extract_base_asset(symbol: str) -> str:
    """Strip common quote-currency suffixes to isolate the base asset."""
    upper = symbol.upper()
    for suffix in _QUOTE_SUFFIXES:
        if upper.endswith(suffix) and len(upper) > len(suffix):
            return upper[: -len(suffix)]
    return upper


def build_query_for_symbol(symbol: str) -> str:
    """Derive a NewsAPI search query from a trading-pair symbol.

    Tries ``BASE_ASSET_QUERY_MAP`` first.  Falls back to
    ``"<base> crypto"`` which is generic but still crypto-scoped.
    """
    base = _extract_base_asset(symbol)
    return BASE_ASSET_QUERY_MAP.get(base, f"{base} crypto")


def _is_noise(title: str) -> bool:
    """Return True if a headline is too short, purely numeric, or spammy."""
    return bool(_NOISE_RE.search(title))


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
    """Fetch news and return a :class:`FetchOutcome` with a machine-readable status."""
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

    query = build_query_for_symbol(symbol)

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
    noise_filtered = 0
    articles: list[NewsArticle] = []
    for art in articles_raw:
        title = (art.get("title") or "").strip()
        if not title or title == "[Removed]":
            continue
        if _is_noise(title):
            noise_filtered += 1
            continue
        articles.append(
            NewsArticle(
                title=title,
                url=art.get("url") or "",
                source=(art.get("source") or {}).get("name", "unknown"),
                published_at=_parse_published(art.get("publishedAt")),
            )
        )

    if noise_filtered:
        logger.info(
            "newsapi_noise_filtered",
            symbol=symbol,
            query=query,
            noise_filtered=noise_filtered,
        )

    if not articles:
        logger.info(
            "newsapi_no_articles_returned",
            symbol=symbol,
            query=query,
        )
        return FetchOutcome(
            status=FetchStatus.NO_ARTICLES,
            detail=(
                f"NewsAPI returned no usable articles for query '{query}' "
                f"(symbol: {symbol}). Check your date range or try a different symbol."
            ),
        )

    return FetchOutcome(status=FetchStatus.OK, articles=articles)
