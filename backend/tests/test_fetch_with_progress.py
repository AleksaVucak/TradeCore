"""Unit tests for fetch_with_progress service (Phase 13.1)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.fetch_job import FetchJob, FetchJobStatus
from app.models.symbol import Symbol
from app.models.user import User
from app.services.market_data.fetch_with_progress import (
    _estimate_total_chunks,
    ingest_candles_with_progress,
)


class TestEstimateTotalChunks:
    def test_returns_zero_for_invalid_range(self) -> None:
        assert _estimate_total_chunks(1000, 500, "1h") == 0

    def test_estimates_1h_chunks(self) -> None:
        start_ms = 0
        end_ms = 1000 * 3600 * 1000 * 3
        result = _estimate_total_chunks(start_ms, end_ms, "1h")
        assert result == 3

    def test_estimates_4h_chunks(self) -> None:
        start_ms = 0
        end_ms = 1000 * 4 * 3600 * 1000 * 2
        result = _estimate_total_chunks(start_ms, end_ms, "4h")
        assert result == 2

    def test_rounds_up_partial_chunks(self) -> None:
        start_ms = 0
        end_ms = int(1000 * 3600 * 1000 * 1.5)
        result = _estimate_total_chunks(start_ms, end_ms, "1h")
        assert result == 2


class TestIngestCandlesWithProgress:
    def test_updates_job_progress(
        self,
        db_session: Session,
        test_user: User,
        test_symbols: list[Symbol],
    ) -> None:
        symbol = test_symbols[0]

        job = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.RUNNING,
        )
        db_session.add(job)
        db_session.flush()

        mock_provider = MagicMock()
        mock_candle = MagicMock()
        mock_candle.timestamp = datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc)
        mock_candle.open = 100.0
        mock_candle.high = 101.0
        mock_candle.low = 99.0
        mock_candle.close = 100.5
        mock_candle.volume = 1000.0

        mock_provider.fetch_klines.side_effect = [[mock_candle], []]

        count = ingest_candles_with_progress(
            db_session,
            job,
            symbol.id,
            "1h",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 2, tzinfo=timezone.utc),
            provider=mock_provider,
        )

        assert count == 1
        assert job.candles_fetched == 1
        assert job.completed_chunks >= 1
        assert job.progress_pct > 0

    def test_raises_for_invalid_symbol(
        self,
        db_session: Session,
        test_user: User,
        test_symbols: list[Symbol],
    ) -> None:
        symbol = test_symbols[0]
        job = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.RUNNING,
        )
        db_session.add(job)
        db_session.flush()

        with pytest.raises(ValueError, match="Symbol id"):
            ingest_candles_with_progress(
                db_session,
                job,
                99999,
                "1h",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
            )

    def test_raises_for_invalid_timeframe(
        self,
        db_session: Session,
        test_user: User,
        test_symbols: list[Symbol],
    ) -> None:
        symbol = test_symbols[0]
        job = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="5m",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.RUNNING,
        )
        db_session.add(job)
        db_session.flush()

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            ingest_candles_with_progress(
                db_session,
                job,
                symbol.id,
                "5m",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
            )

    def test_raises_for_invalid_date_range(
        self,
        db_session: Session,
        test_user: User,
        test_symbols: list[Symbol],
    ) -> None:
        symbol = test_symbols[0]
        job = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            status=FetchJobStatus.RUNNING,
        )
        db_session.add(job)
        db_session.flush()

        with pytest.raises(ValueError, match="start_date must be before"):
            ingest_candles_with_progress(
                db_session,
                job,
                symbol.id,
                "1h",
                datetime(2025, 1, 2, tzinfo=timezone.utc),
                datetime(2025, 1, 1, tzinfo=timezone.utc),
            )
