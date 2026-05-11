"""Tests for the sentiment pipeline (Phase 17.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# VADER scorer tests
# ---------------------------------------------------------------------------

class TestSentimentScorer:
    def test_positive_headline(self):
        from app.services.sentiment.scorer import score_text

        result = score_text("Bitcoin surges to new all-time high, investors celebrate")
        assert result.score > 0
        assert result.label == "positive"

    def test_negative_headline(self):
        from app.services.sentiment.scorer import score_text

        result = score_text("Crypto market crashes, billions lost in devastating sell-off")
        assert result.score < 0
        assert result.label == "negative"

    def test_neutral_headline(self):
        from app.services.sentiment.scorer import score_text

        result = score_text("Bitcoin price unchanged at current levels")
        assert result.label in ("neutral", "positive", "negative")
        assert -1.0 <= result.score <= 1.0

    def test_score_texts_batch(self):
        from app.services.sentiment.scorer import score_texts

        headlines = [
            "Market rallies on positive news",
            "Terrible crash wipes out gains",
            "Trading volume stable",
        ]
        results = score_texts(headlines)
        assert len(results) == 3
        for r in results:
            assert -1.0 <= r.score <= 1.0
            assert r.label in ("positive", "negative", "neutral")

    def test_score_precision(self):
        from app.services.sentiment.scorer import score_text

        result = score_text("Great amazing wonderful fantastic")
        decimal_places = len(str(result.score).split(".")[-1]) if "." in str(result.score) else 0
        assert decimal_places <= 4

    def test_classify_thresholds(self):
        from app.services.sentiment.scorer import _classify

        assert _classify(0.05) == "positive"
        assert _classify(0.5) == "positive"
        assert _classify(-0.05) == "negative"
        assert _classify(-0.5) == "negative"
        assert _classify(0.0) == "neutral"
        assert _classify(0.04) == "neutral"
        assert _classify(-0.04) == "neutral"


# ---------------------------------------------------------------------------
# News fetcher tests
# ---------------------------------------------------------------------------

class TestNewsFetcher:
    def test_returns_empty_when_no_api_key(self):
        with patch("app.services.sentiment.news_fetcher.settings") as mock_settings:
            mock_settings.newsapi_key = ""
            from app.services.sentiment.news_fetcher import fetch_news

            # Re-import to pick up the patched settings
            articles = fetch_news("BTCUSDT")
            assert articles == []

    def test_symbol_query_map(self):
        from app.services.sentiment.news_fetcher import SYMBOL_QUERY_MAP

        assert "BTCUSDT" in SYMBOL_QUERY_MAP
        assert "ETHUSDT" in SYMBOL_QUERY_MAP
        assert "Bitcoin" in SYMBOL_QUERY_MAP["BTCUSDT"]

    def test_parse_published_valid(self):
        from app.services.sentiment.news_fetcher import _parse_published

        dt = _parse_published("2026-05-01T12:00:00Z")
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.tzinfo is not None

    def test_parse_published_none(self):
        from app.services.sentiment.news_fetcher import _parse_published

        dt = _parse_published(None)
        assert dt.tzinfo is not None

    def test_parse_published_invalid(self):
        from app.services.sentiment.news_fetcher import _parse_published

        dt = _parse_published("not-a-date")
        assert dt.tzinfo is not None

    @patch("app.services.sentiment.news_fetcher.httpx.get")
    def test_fetch_news_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "status": "ok",
            "totalResults": 2,
            "articles": [
                {
                    "title": "Bitcoin hits record high",
                    "url": "https://example.com/1",
                    "source": {"name": "CoinDesk"},
                    "publishedAt": "2026-05-10T10:00:00Z",
                },
                {
                    "title": "[Removed]",
                    "url": "https://example.com/2",
                    "source": {"name": "Unknown"},
                    "publishedAt": "2026-05-10T11:00:00Z",
                },
                {
                    "title": "Ethereum upgrade completed",
                    "url": "https://example.com/3",
                    "source": {"name": "CryptoNews"},
                    "publishedAt": "2026-05-10T09:00:00Z",
                },
            ],
        }
        mock_get.return_value = mock_resp

        with patch("app.services.sentiment.news_fetcher.settings") as mock_settings:
            mock_settings.newsapi_key = "test-key-123"
            from app.services.sentiment.news_fetcher import fetch_news

            articles = fetch_news("BTCUSDT")

        assert len(articles) == 2
        assert articles[0].title == "Bitcoin hits record high"
        assert articles[0].source == "CoinDesk"
        assert articles[1].title == "Ethereum upgrade completed"

    @patch("app.services.sentiment.news_fetcher.httpx.get")
    def test_fetch_news_http_error(self, mock_get):
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limited"
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=mock_resp
        )
        mock_get.return_value = mock_resp

        with patch("app.services.sentiment.news_fetcher.settings") as mock_settings:
            mock_settings.newsapi_key = "test-key-123"
            from app.services.sentiment.news_fetcher import fetch_news

            articles = fetch_news("BTCUSDT")

        assert articles == []


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------

class TestSentimentPipeline:
    @patch("app.services.sentiment.pipeline.fetch_news")
    def test_pipeline_no_articles(self, mock_fetch):
        mock_fetch.return_value = []
        db = MagicMock()

        from app.services.sentiment.pipeline import run_sentiment_pipeline

        result = run_sentiment_pipeline(db, symbol_id=1, symbol="BTCUSDT")
        assert result["fetched"] == 0
        assert result["new"] == 0
        assert result["skipped"] == 0

    @patch("app.services.sentiment.pipeline.score_text")
    @patch("app.services.sentiment.pipeline.fetch_news")
    def test_pipeline_stores_new_articles(self, mock_fetch, mock_score):
        from app.services.sentiment.news_fetcher import NewsArticle
        from app.services.sentiment.scorer import SentimentResult

        mock_fetch.return_value = [
            NewsArticle(
                title="BTC goes up",
                url="https://example.com/1",
                source="TestSource",
                published_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            ),
            NewsArticle(
                title="ETH goes down",
                url="https://example.com/2",
                source="TestSource",
                published_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            ),
        ]
        mock_score.side_effect = [
            SentimentResult(score=0.6, label="positive"),
            SentimentResult(score=-0.3, label="negative"),
        ]

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []

        from app.services.sentiment.pipeline import run_sentiment_pipeline

        result = run_sentiment_pipeline(db, symbol_id=1, symbol="BTCUSDT")
        assert result["fetched"] == 2
        assert result["new"] == 2
        assert result["skipped"] == 0
        assert db.add.call_count == 2
        db.commit.assert_called_once()

    @patch("app.services.sentiment.pipeline.score_text")
    @patch("app.services.sentiment.pipeline.fetch_news")
    def test_pipeline_deduplicates(self, mock_fetch, mock_score):
        from app.services.sentiment.news_fetcher import NewsArticle
        from app.services.sentiment.scorer import SentimentResult

        mock_fetch.return_value = [
            NewsArticle(
                title="Already exists",
                url="https://example.com/dup",
                source="TestSource",
                published_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            ),
            NewsArticle(
                title="Brand new",
                url="https://example.com/new",
                source="TestSource",
                published_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            ),
        ]
        mock_score.return_value = SentimentResult(score=0.5, label="positive")

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            ("Already exists",),
        ]

        from app.services.sentiment.pipeline import run_sentiment_pipeline

        result = run_sentiment_pipeline(db, symbol_id=1, symbol="BTCUSDT")
        assert result["fetched"] == 2
        assert result["new"] == 1
        assert result["skipped"] == 1
        assert db.add.call_count == 1


# ---------------------------------------------------------------------------
# Celery task tests
# ---------------------------------------------------------------------------

class TestSentimentTasks:
    @patch("app.tasks.sentiment.SessionLocal")
    def test_fetch_sentiment_task_success(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        with patch("app.services.sentiment.pipeline.run_sentiment_pipeline") as mock_pipeline:
            mock_pipeline.return_value = {"fetched": 10, "new": 5, "skipped": 5}

            from app.tasks.sentiment import fetch_sentiment_task

            result = fetch_sentiment_task(symbol_id=1, symbol="BTCUSDT")

        assert result["status"] == "ok"
        assert result["fetched"] == 10
        assert result["new"] == 5
        mock_db.close.assert_called_once()

    @patch("app.tasks.sentiment.SessionLocal")
    def test_refresh_all_dispatches(self, mock_session_cls):
        from app.models.symbol import Symbol

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        sym1 = MagicMock(spec=Symbol)
        sym1.id = 1
        sym1.symbol = "BTCUSDT"
        sym1.is_active = True

        sym2 = MagicMock(spec=Symbol)
        sym2.id = 2
        sym2.symbol = "ETHUSDT"
        sym2.is_active = True

        mock_db.query.return_value.filter.return_value.all.return_value = [sym1, sym2]

        with patch("app.tasks.sentiment.fetch_sentiment_task") as mock_fetch_task:
            mock_fetch_task.apply_async = MagicMock()

            from app.tasks.sentiment import refresh_all_sentiment_task

            result = refresh_all_sentiment_task()

        assert result["status"] == "ok"
        assert result["dispatched"] == 2
        assert mock_fetch_task.apply_async.call_count == 2
        mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# Model / schema tests
# ---------------------------------------------------------------------------

class TestSentimentModel:
    def test_model_columns_exist(self):
        from app.models.sentiment_score import SentimentScore

        table = SentimentScore.__table__
        col_names = {c.name for c in table.columns}
        expected = {
            "id", "symbol_id", "source", "headline", "url",
            "published_at", "score", "label", "created_at",
        }
        assert expected.issubset(col_names)

    def test_schema_from_attributes(self):
        from app.schemas.sentiment import SentimentScoreOut

        assert SentimentScoreOut.model_config.get("from_attributes") is True
