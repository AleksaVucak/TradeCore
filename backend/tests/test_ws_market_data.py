"""WebSocket tests for market data progress endpoint (Phase 13.4)."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.api import ws_market_data
from app.core.security import create_access_token
from app.models.fetch_job import FetchJob, FetchJobStatus
from app.models.symbol import Symbol
from app.models.user import User


class _SessionFactory:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __call__(self) -> Session:
        return self._session


class TestMarketDataProgressWebSocket:
    def test_streams_job_snapshot_for_owner(
        self,
        client: TestClient,
        db_session: Session,
        monkeypatch: MonkeyPatch,
        test_user: User,
        test_symbols: list[Symbol],
    ) -> None:
        monkeypatch.setattr(ws_market_data, "SessionLocal", _SessionFactory(db_session))
        symbol = test_symbols[0]
        job = FetchJob(
            user_id=test_user.id,
            symbol_id=symbol.id,
            timeframe="1h",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            status=FetchJobStatus.RUNNING,
            total_chunks=10,
            completed_chunks=4,
            candles_fetched=400,
            progress_pct=40.0,
        )
        db_session.add(job)
        db_session.flush()

        token = create_access_token(subject=test_user.id)
        with client.websocket_connect(f"/ws/market-data/{job.id}?token={token}") as websocket:
            data = websocket.receive_json()

        assert data["job_id"] == str(job.id)
        assert data["status"] == "running"
        assert data["total_chunks"] == 10
        assert data["completed_chunks"] == 4
        assert data["candles_fetched"] == 400
        assert data["progress_pct"] == 40.0

    def test_rejects_missing_token(
        self,
        client: TestClient,
        db_session: Session,
        monkeypatch: MonkeyPatch,
        test_user: User,
        test_symbols: list[Symbol],
    ) -> None:
        monkeypatch.setattr(ws_market_data, "SessionLocal", _SessionFactory(db_session))
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

        try:
            with client.websocket_connect(f"/ws/market-data/{job.id}"):
                assert False, "Expected websocket connection to be rejected"
        except WebSocketDisconnect as exc:
            assert exc.code == 4401

    def test_rejects_other_users_job(
        self,
        client: TestClient,
        db_session: Session,
        monkeypatch: MonkeyPatch,
        other_user: User,
        test_user: User,
        test_symbols: list[Symbol],
    ) -> None:
        monkeypatch.setattr(ws_market_data, "SessionLocal", _SessionFactory(db_session))
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

        token = create_access_token(subject=test_user.id)
        try:
            with client.websocket_connect(f"/ws/market-data/{job.id}?token={token}") as websocket:
                websocket.receive_json()
                assert False, "Expected websocket connection to be rejected"
        except WebSocketDisconnect as exc:
            assert exc.code == 4404

    def test_rejects_invalid_token(
        self,
        client: TestClient,
    ) -> None:
        fake_id = uuid4()
        try:
            with client.websocket_connect(f"/ws/market-data/{fake_id}?token=bad-token"):
                assert False, "Expected websocket connection to be rejected"
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
