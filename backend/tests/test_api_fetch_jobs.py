"""API tests for market data fetch endpoints (Phase 13.1)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.fetch_job import FetchJob, FetchJobStatus
from app.models.symbol import Symbol
from app.models.user import User


class TestPostFetch:
    """Tests for POST /api/v1/market-data/fetch"""

    def test_creates_fetch_job_and_returns_202(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        symbol = test_symbols[0]
        with patch("app.api.v1.market_data.fetch_candles_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-123")
            resp = client.post(
                "/api/v1/market-data/fetch",
                json={
                    "symbol_id": symbol.id,
                    "timeframe": "1h",
                    "start_date": "2025-01-01T00:00:00Z",
                    "end_date": "2025-01-02T00:00:00Z",
                },
                headers=auth_headers,
            )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["symbol_id"] == symbol.id
        assert data["timeframe"] == "1h"
        assert data["message"] == "Fetch job started"

    def test_rejects_invalid_timeframe(
        self,
        client: TestClient,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        symbol = test_symbols[0]
        resp = client.post(
            "/api/v1/market-data/fetch",
            json={
                "symbol_id": symbol.id,
                "timeframe": "5m",
                "start_date": "2025-01-01T00:00:00Z",
                "end_date": "2025-01-02T00:00:00Z",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_rejects_end_before_start(
        self,
        client: TestClient,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        symbol = test_symbols[0]
        resp = client.post(
            "/api/v1/market-data/fetch",
            json={
                "symbol_id": symbol.id,
                "timeframe": "1h",
                "start_date": "2025-01-02T00:00:00Z",
                "end_date": "2025-01-01T00:00:00Z",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_rejects_invalid_symbol(
        self,
        client: TestClient,
        auth_headers: dict,
    ) -> None:
        resp = client.post(
            "/api/v1/market-data/fetch",
            json={
                "symbol_id": 99999,
                "timeframe": "1h",
                "start_date": "2025-01-01T00:00:00Z",
                "end_date": "2025-01-02T00:00:00Z",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_requires_auth(
        self,
        client: TestClient,
        test_symbols: list[Symbol],
    ) -> None:
        symbol = test_symbols[0]
        resp = client.post(
            "/api/v1/market-data/fetch",
            json={
                "symbol_id": symbol.id,
                "timeframe": "1h",
                "start_date": "2025-01-01T00:00:00Z",
                "end_date": "2025-01-02T00:00:00Z",
            },
        )
        assert resp.status_code == 401


class TestGetFetchStatus:
    """Tests for GET /api/v1/market-data/fetch/{job_id}"""

    def test_returns_job_status(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        symbol = test_symbols[0]
        job = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.RUNNING,
            total_chunks=10,
            completed_chunks=5,
            candles_fetched=500,
            progress_pct=50.0,
        )
        db_session.add(job)
        db_session.flush()

        resp = client.get(f"/api/v1/market-data/fetch/{job.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == str(job.id)
        assert data["status"] == "running"
        assert data["total_chunks"] == 10
        assert data["completed_chunks"] == 5
        assert data["candles_fetched"] == 500
        assert data["progress_pct"] == 50.0

    def test_returns_404_for_nonexistent_job(
        self,
        client: TestClient,
        auth_headers: dict,
    ) -> None:
        fake_id = uuid4()
        resp = client.get(f"/api/v1/market-data/fetch/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_returns_404_for_other_users_job(
        self,
        client: TestClient,
        db_session: Session,
        other_user: User,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        symbol = test_symbols[0]
        job = FetchJob(
            user_id=other_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.PENDING,
        )
        db_session.add(job)
        db_session.flush()

        resp = client.get(f"/api/v1/market-data/fetch/{job.id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_requires_auth(
        self,
        client: TestClient,
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
            status=FetchJobStatus.PENDING,
        )
        db_session.add(job)
        db_session.flush()

        resp = client.get(f"/api/v1/market-data/fetch/{job.id}")
        assert resp.status_code == 401


class TestListFetchJobs:
    """Tests for GET /api/v1/market-data/fetch"""

    def test_returns_users_jobs(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        symbol = test_symbols[0]
        job1 = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.COMPLETED,
        )
        job2 = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="4h",
            start_date=datetime(2025, 1, 3, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 4, tzinfo=timezone.utc),
            status=FetchJobStatus.PENDING,
        )
        db_session.add_all([job1, job2])
        db_session.flush()

        resp = client.get("/api/v1/market-data/fetch", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        job_ids = [j["job_id"] for j in data]
        assert str(job1.id) in job_ids
        assert str(job2.id) in job_ids

    def test_filters_by_status(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        symbol = test_symbols[0]
        job_completed = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.COMPLETED,
        )
        job_pending = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 3, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 4, tzinfo=timezone.utc),
            status=FetchJobStatus.PENDING,
        )
        db_session.add_all([job_completed, job_pending])
        db_session.flush()

        resp = client.get(
            "/api/v1/market-data/fetch?status=completed", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        for job in data:
            assert job["status"] == "completed"

    def test_excludes_other_users_jobs(
        self,
        client: TestClient,
        db_session: Session,
        other_user: User,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        symbol = test_symbols[0]
        job = FetchJob(
            user_id=other_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.PENDING,
        )
        db_session.add(job)
        db_session.flush()

        resp = client.get("/api/v1/market-data/fetch", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        job_ids = [j["job_id"] for j in data]
        assert str(job.id) not in job_ids

    def test_requires_auth(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/api/v1/market-data/fetch")
        assert resp.status_code == 401
