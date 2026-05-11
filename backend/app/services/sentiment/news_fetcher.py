"""News headline fetcher using NewsAPI (Phase 17.1).

Fetches recent English-language news articles for a given query term
(typically a crypto symbol like "Bitcoin" or "Ethereum") and returns
a list of structured article dicts ready for sentiment scoring.

Requires NEWSAPI_KEY to be set in the environment / Settings.
When the key is empty, returns an empty list with a warning log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"

SYMBOL_QUERY_MAP: dict[str, str] = {
    "BTCUSDT": "Bitcoin OR BTC",
    "ETHUSDT": "Ethereum OR ETH",
}

DEFAULT_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class NewsArticle:
    title: str
    url: str
    source: str
    published_at: datetime


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

    Args:
        symbol: Trading pair symbol (e.g. "BTCUSDT"). Mapped to a search query
                via SYMBOL_QUERY_MAP; falls back to the raw symbol string.
        page_size: Number of articles to request (max 100 for free tier).
        from_date: Optional ISO date string to limit results (e.g. "2026-05-01").
        to_date: Optional ISO date string for the upper bound.

    Returns:
        List of NewsArticle objects sorted newest-first.
    """
    api_key = settings.newsapi_key
    if not api_key:
        logger.warning("newsapi_key_not_set", hint="Set NEWSAPI_KEY in .env to enable news fetching")
        return []

    query = SYMBOL_QUERY_MAP.get(symbol, symbol)

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
        logger.error(
            "newsapi_http_error",
            status_code=exc.response.status_code,
            body=exc.response.text[:500],
        )
        return []
    except httpx.RequestError as exc:
        logger.error("newsapi_request_error", error=str(exc))
        return []

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

    return articles
