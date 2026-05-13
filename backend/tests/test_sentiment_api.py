"""API tests for sentiment endpoints (Phase 17.2 + 17.7).

Uses the transactional test fixtures from conftest.py so each test
is isolated and rolled back automatically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.sentiment_score import SentimentScore
from app.models.symbol import Symbol
from app.models.user import User

_SEED_BATCH_COUNTER = count()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_symbol(db: Session, symbol: str, base: str, quote: str) -> Symbol:
    existing = db.query(Symbol).filter(Symbol.symbol == symbol).first()
    if existing:
        # Keep tests deterministic even if local/dev DB already has sentiment rows
        # for this symbol from manual testing.
        db.query(SentimentScore).filter(SentimentScore.symbol_id == existing.id).delete()
        db.flush()
        return existing
    s = Symbol(symbol=symbol, base_asset=base, quote_asset=quote, is_active=True)
    db.add(s)
    db.flush()
    return s


def _seed_sentiment(
    db: Session,
    symbol_id: int,
    count: int = 5,
    *,
    base_time: datetime | None = None,
    label: str = "positive",
    score: float = 0.5,
) -> list[SentimentScore]:
    """Insert `count` sentiment rows and return them."""
    base = base_time or datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    batch = next(_SEED_BATCH_COUNTER)
    rows = []
    for i in range(count):
        row = SentimentScore(
            symbol_id=symbol_id,
            source="TestSource",
            headline=f"Test headline b{batch}-{i}",
            url=f"https://example.com/b{batch}/{i}",
            published_at=base - timedelta(hours=i),
            score=score,
            label=label,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


# ---------------------------------------------------------------------------
# GET /api/v1/sentiment/{symbol} tests
# ---------------------------------------------------------------------------

class TestGetSentimentForSymbol:
    def test_returns_scores(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        _seed_sentiment(db_session, sym.id, count=3)

        resp = client.get(f"/api/v1/sentiment/{sym.symbol}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "BTCUSD"
        assert data["symbol_id"] == sym.id
        assert data["count"] == 3
        assert len(data["scores"]) == 3

    def test_returns_empty_list_when_no_data(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")

        resp = client.get(f"/api/v1/sentiment/{sym.symbol}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["scores"] == []

    def test_404_for_unknown_symbol(
        self, client: TestClient, auth_headers: dict, test_user: User
    ):
        resp = client.get("/api/v1/sentiment/NOSUCHSYMBOL", headers=auth_headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_requires_auth(self, client: TestClient, db_session: Session, test_user: User):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        resp = client.get(f"/api/v1/sentiment/{sym.symbol}")
        assert resp.status_code == 401

    def test_limit_parameter(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        _seed_sentiment(db_session, sym.id, count=10)

        resp = client.get(
            f"/api/v1/sentiment/{sym.symbol}?limit=3", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert len(data["scores"]) == 3

    def test_label_filter(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        _seed_sentiment(db_session, sym.id, count=3, label="positive", score=0.5)
        _seed_sentiment(db_session, sym.id, count=2, label="negative", score=-0.5)

        resp = client.get(
            f"/api/v1/sentiment/{sym.symbol}?label=negative", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        for s in data["scores"]:
            assert s["label"] == "negative"

    def test_invalid_label(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")

        resp = client.get(
            f"/api/v1/sentiment/{sym.symbol}?label=invalid", headers=auth_headers
        )
        assert resp.status_code == 422
        assert "Invalid label" in resp.json()["detail"]

    def test_date_range_filter(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        recent_time = datetime(2026, 5, 10, tzinfo=timezone.utc)
        _seed_sentiment(db_session, sym.id, count=2, base_time=old_time)
        _seed_sentiment(db_session, sym.id, count=3, base_time=recent_time)

        start = "2026-05-01T00:00:00Z"
        resp = client.get(
            f"/api/v1/sentiment/{sym.symbol}?start={start}", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3

    def test_case_insensitive_symbol(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        _seed_sentiment(db_session, sym.id, count=2)

        resp = client.get("/api/v1/sentiment/btcusd", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "BTCUSD"

    def test_scores_ordered_by_published_at_desc(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        _seed_sentiment(db_session, sym.id, count=5)

        resp = client.get(f"/api/v1/sentiment/{sym.symbol}", headers=auth_headers)
        data = resp.json()
        timestamps = [s["published_at"] for s in data["scores"]]
        assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# GET /api/v1/sentiment/{symbol}/aggregate tests
# ---------------------------------------------------------------------------

class TestGetSentimentAggregate:
    def test_returns_aggregate_stats(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        _seed_sentiment(db_session, sym.id, count=3, label="positive", score=0.6)
        _seed_sentiment(db_session, sym.id, count=2, label="negative", score=-0.4)

        resp = client.get(f"/api/v1/sentiment/{sym.symbol}/aggregate", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "BTCUSD"
        assert data["total"] == 5
        assert data["positive_count"] == 3
        assert data["negative_count"] == 2
        assert data["neutral_count"] == 0
        assert data["overall_label"] == "positive"
        assert isinstance(data["avg_score"], float)

    def test_empty_aggregate(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")

        resp = client.get(f"/api/v1/sentiment/{sym.symbol}/aggregate", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["avg_score"] == 0.0
        assert data["overall_label"] == "neutral"

    def test_404_for_unknown_symbol(
        self, client: TestClient, auth_headers: dict, test_user: User
    ):
        resp = client.get("/api/v1/sentiment/NOSUCHSYMBOL/aggregate", headers=auth_headers)
        assert resp.status_code == 404

    def test_requires_auth(self, client: TestClient, db_session: Session, test_user: User):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        resp = client.get(f"/api/v1/sentiment/{sym.symbol}/aggregate")
        assert resp.status_code == 401

    def test_date_filtered_aggregate(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        recent_time = datetime(2026, 5, 10, tzinfo=timezone.utc)
        _seed_sentiment(db_session, sym.id, count=2, base_time=old_time, label="negative", score=-0.5)
        _seed_sentiment(db_session, sym.id, count=3, base_time=recent_time, label="positive", score=0.5)

        resp = client.get(
            f"/api/v1/sentiment/{sym.symbol}/aggregate?start=2026-05-01T00:00:00Z",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["positive_count"] == 3
        assert data["negative_count"] == 0


# ---------------------------------------------------------------------------
# POST /api/v1/sentiment/refresh tests
# ---------------------------------------------------------------------------

class TestTriggerSentimentRefresh:
    @patch("app.tasks.sentiment.fetch_sentiment_task")
    def test_enqueues_task(
        self,
        mock_task,
        client: TestClient,
        db_session: Session,
        auth_headers: dict,
        test_user: User,
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        mock_result = MagicMock()
        mock_result.id = "fake-task-id-123"
        mock_task.apply_async.return_value = mock_result

        resp = client.post(
            "/api/v1/sentiment/refresh",
            json={"symbol_id": sym.id, "lookback_days": 7},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["task_id"] == "fake-task-id-123"
        mock_task.apply_async.assert_called_once()

    def test_404_for_unknown_symbol_id(
        self, client: TestClient, auth_headers: dict, test_user: User
    ):
        resp = client.post(
            "/api/v1/sentiment/refresh",
            json={"symbol_id": 99999},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client: TestClient, db_session: Session, test_user: User):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        resp = client.post(
            "/api/v1/sentiment/refresh",
            json={"symbol_id": sym.id},
        )
        assert resp.status_code == 401

    @patch("app.tasks.sentiment.fetch_sentiment_task")
    def test_default_lookback_days(
        self,
        mock_task,
        client: TestClient,
        db_session: Session,
        auth_headers: dict,
        test_user: User,
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        mock_result = MagicMock()
        mock_result.id = "task-456"
        mock_task.apply_async.return_value = mock_result

        resp = client.post(
            "/api/v1/sentiment/refresh",
            json={"symbol_id": sym.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        call_kwargs = mock_task.apply_async.call_args.kwargs["kwargs"]
        assert call_kwargs["lookback_days"] == 7


# ---------------------------------------------------------------------------
# GET /api/v1/sentiment/status tests (Phase 17.5)
# ---------------------------------------------------------------------------

class TestGetSentimentStatus:
    def test_returns_status_with_symbols(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        _seed_sentiment(db_session, sym.id, count=5)

        resp = client.get("/api/v1/sentiment/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "newsapi_key_set" in data
        assert isinstance(data["symbols"], list)
        btc_item = next((s for s in data["symbols"] if s["symbol"] == "BTCUSD"), None)
        assert btc_item is not None
        assert btc_item["total_scores"] == 5
        assert btc_item["newest_published_at"] is not None

    def test_returns_empty_counts_for_new_symbol(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        _get_or_create_symbol(db_session, "DOTUSDT", "DOT", "USDT")

        resp = client.get("/api/v1/sentiment/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        dot_item = next((s for s in data["symbols"] if s["symbol"] == "DOTUSDT"), None)
        assert dot_item is not None
        assert dot_item["total_scores"] == 0
        assert dot_item["newest_published_at"] is None

    def test_staleness_fields_present(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        """Phase 17.7: status items should include staleness indicators."""
        sym = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD")
        _seed_sentiment(db_session, sym.id, count=3)

        resp = client.get("/api/v1/sentiment/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        btc_item = next((s for s in data["symbols"] if s["symbol"] == "BTCUSD"), None)
        assert btc_item is not None
        assert "last_refreshed_at" in btc_item
        assert "data_age_hours" in btc_item
        assert "is_stale" in btc_item
        assert isinstance(btc_item["data_age_hours"], float)
        assert isinstance(btc_item["is_stale"], bool)

    def test_new_symbol_staleness_defaults(
        self, client: TestClient, db_session: Session, auth_headers: dict, test_user: User
    ):
        """Phase 17.7: symbols with no data should have null age and is_stale=True."""
        _get_or_create_symbol(db_session, "NEWCOIN", "NEW", "USDT")

        resp = client.get("/api/v1/sentiment/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        item = next((s for s in data["symbols"] if s["symbol"] == "NEWCOIN"), None)
        assert item is not None
        assert item["data_age_hours"] is None
        assert item["last_refreshed_at"] is None
        assert item["is_stale"] is True

    def test_requires_auth(self, client: TestClient):
        resp = client.get("/api/v1/sentiment/status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSentimentSchemas:
    def test_sentiment_symbol_response_schema(self):
        from app.schemas.sentiment import SentimentSymbolResponse

        resp = SentimentSymbolResponse(
            symbol="BTCUSD",
            symbol_id=1,
            count=0,
            scores=[],
        )
        assert resp.symbol == "BTCUSD"
        assert resp.count == 0

    def test_sentiment_aggregate_schema(self):
        from app.schemas.sentiment import SentimentAggregateOut

        agg = SentimentAggregateOut(
            symbol="BTCUSD",
            symbol_id=1,
            total=10,
            avg_score=0.25,
            positive_count=6,
            negative_count=3,
            neutral_count=1,
            overall_label="positive",
        )
        assert agg.total == 10
        assert agg.overall_label == "positive"

    def test_status_item_schema(self):
        from app.schemas.sentiment import SentimentStatusItem

        item = SentimentStatusItem(
            symbol="BTCUSD",
            symbol_id=1,
            total_scores=0,
        )
        assert item.newest_published_at is None
        assert item.total_scores == 0
        assert item.last_refreshed_at is None
        assert item.data_age_hours is None
        assert item.is_stale is False

    def test_status_item_with_staleness(self):
        """Phase 17.7: SentimentStatusItem with all staleness fields set."""
        from app.schemas.sentiment import SentimentStatusItem

        item = SentimentStatusItem(
            symbol="ETHUSD",
            symbol_id=2,
            total_scores=50,
            newest_published_at="2026-05-10T12:00:00Z",
            oldest_published_at="2026-05-03T06:00:00Z",
            last_refreshed_at="2026-05-10T13:00:00Z",
            data_age_hours=12.5,
            is_stale=False,
        )
        assert item.data_age_hours == 12.5
        assert item.is_stale is False
        assert item.last_refreshed_at is not None
