"""API tests for backtests endpoints (Phase 11.2)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.backtest_run import BacktestRun, BacktestRunStatus
from app.models.equity_snapshot import EquitySnapshot
from app.models.metric_snapshot import MetricSnapshot
from app.models.strategy import Strategy, StrategyVersion
from app.models.symbol import Symbol
from app.models.trade import Trade
from app.models.user import User

VALID_CONFIG = {
    "rsi_period": 14,
    "rsi_buy_threshold": 30.0,
    "rsi_sell_threshold": 70.0,
    "ma_period": 20,
}


@pytest.fixture()
def strategy_and_version(db_session: Session, test_user: User):
    """Create a strategy + active version, return (strategy, version)."""
    s = Strategy(
        user_id=test_user.id,
        name="Test Strategy",
        description="For backtest tests",
        strategy_type="rsi_ma",
    )
    db_session.add(s)
    db_session.flush()
    v = StrategyVersion(
        strategy_id=s.id,
        version_number=1,
        config=VALID_CONFIG,
        is_active=True,
    )
    db_session.add(v)
    db_session.flush()
    return s, v


@pytest.fixture()
def btc_symbol(db_session: Session) -> Symbol:
    existing = db_session.query(Symbol).filter(Symbol.symbol == "BTCUSD").first()
    if existing:
        return existing
    sym = Symbol(symbol="BTCUSD", base_asset="BTC", quote_asset="USD", is_active=True)
    db_session.add(sym)
    db_session.flush()
    return sym


def _create_completed_run(
    db: Session,
    user: User,
    version: StrategyVersion,
    symbol: Symbol,
    *,
    with_trades: bool = True,
    with_equity: bool = True,
    with_metrics: bool = True,
) -> BacktestRun:
    """Helper to create a completed backtest run with optional children."""
    run = BacktestRun(
        user_id=user.id,
        strategy_version_id=version.id,
        symbol_id=symbol.id,
        timeframe="1h",
        start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
        status=BacktestRunStatus.COMPLETED,
    )
    db.add(run)
    db.flush()

    if with_trades:
        t1 = Trade(
            backtest_run_id=run.id,
            timestamp=datetime(2025, 1, 10, tzinfo=timezone.utc),
            side="buy",
            price=40000.0,
            quantity=0.1,
            fee=4.0,
            slippage=0.0,
            pnl=None,
        )
        t2 = Trade(
            backtest_run_id=run.id,
            timestamp=datetime(2025, 1, 20, tzinfo=timezone.utc),
            side="sell",
            price=42000.0,
            quantity=0.1,
            fee=4.2,
            slippage=0.0,
            pnl=191.8,
        )
        db.add_all([t1, t2])

    if with_equity:
        for i, eq in enumerate([10000.0, 10100.0, 10191.8]):
            db.add(
                EquitySnapshot(
                    backtest_run_id=run.id,
                    timestamp=datetime(2025, 1, 1 + i * 10, tzinfo=timezone.utc),
                    equity_value=eq,
                )
            )

    if with_metrics:
        db.add(
            MetricSnapshot(
                backtest_run_id=run.id,
                metrics={
                    "total_return_pct": 1.92,
                    "max_drawdown_pct": 0.5,
                    "num_trades": 2,
                    "final_equity": 10191.8,
                },
            )
        )

    db.flush()
    return run


class TestListBacktests:
    def test_list_own_runs(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        _create_completed_run(db_session, test_user, v, btc_symbol)
        resp = client.get("/api/v1/backtests", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        item = data[0]
        assert "id" in item
        assert item["status"] == "completed"
        assert item["symbol_name"] == "BTCUSD"

    def test_does_not_list_other_users_runs(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        other_user: User,
        auth_headers: dict,
        btc_symbol: Symbol,
    ) -> None:
        s = Strategy(
            user_id=other_user.id,
            name="Other Strat",
            strategy_type="rsi_ma",
        )
        db_session.add(s)
        db_session.flush()
        v = StrategyVersion(
            strategy_id=s.id, version_number=1, config=VALID_CONFIG, is_active=True
        )
        db_session.add(v)
        db_session.flush()
        _create_completed_run(db_session, other_user, v, btc_symbol)

        resp = client.get("/api/v1/backtests", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/v1/backtests")
        assert resp.status_code == 401


class TestCreateBacktest:
    @patch("app.api.v1.backtests.run_backtest_task")
    def test_create_success(
        self,
        mock_task,
        client: TestClient,
        db_session: Session,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        mock_task.delay = MagicMock()
        _, v = strategy_and_version
        resp = client.post(
            "/api/v1/backtests",
            json={
                "strategy_version_id": v.id,
                "symbol_id": btc_symbol.id,
                "timeframe": "1h",
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-06-01T00:00:00Z",
                "initial_equity": 10000,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["timeframe"] == "1h"
        mock_task.delay.assert_called_once()

    @patch("app.api.v1.backtests.run_backtest_task")
    def test_create_start_after_end(
        self,
        mock_task,
        client: TestClient,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        resp = client.post(
            "/api/v1/backtests",
            json={
                "strategy_version_id": v.id,
                "symbol_id": btc_symbol.id,
                "timeframe": "1h",
                "start_time": "2025-06-01T00:00:00Z",
                "end_time": "2025-01-01T00:00:00Z",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400

    @patch("app.api.v1.backtests.run_backtest_task")
    def test_create_nonexistent_symbol(
        self,
        mock_task,
        client: TestClient,
        auth_headers: dict,
        strategy_and_version,
    ) -> None:
        _, v = strategy_and_version
        resp = client.post(
            "/api/v1/backtests",
            json={
                "strategy_version_id": v.id,
                "symbol_id": 99999,
                "timeframe": "1h",
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-06-01T00:00:00Z",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @patch("app.api.v1.backtests.run_backtest_task")
    def test_create_other_users_version(
        self,
        mock_task,
        client: TestClient,
        db_session: Session,
        other_user: User,
        auth_headers: dict,
        btc_symbol: Symbol,
    ) -> None:
        s = Strategy(
            user_id=other_user.id, name="Other", strategy_type="rsi_ma"
        )
        db_session.add(s)
        db_session.flush()
        v = StrategyVersion(
            strategy_id=s.id, version_number=1, config=VALID_CONFIG, is_active=True
        )
        db_session.add(v)
        db_session.flush()

        resp = client.post(
            "/api/v1/backtests",
            json={
                "strategy_version_id": v.id,
                "symbol_id": btc_symbol.id,
                "timeframe": "1h",
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-06-01T00:00:00Z",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_create_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/backtests",
            json={
                "strategy_version_id": 1,
                "symbol_id": 1,
                "timeframe": "1h",
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-06-01T00:00:00Z",
            },
        )
        assert resp.status_code == 401


class TestGetBacktest:
    def test_get_own_run(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run(db_session, test_user, v, btc_symbol)
        resp = client.get(f"/api/v1/backtests/{run.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(run.id)
        assert data["status"] == "completed"
        assert len(data["trades"]) == 2
        assert len(data["equity_curve"]) == 3
        assert data["metrics"] is not None

    def test_get_other_users_run_404(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        other_user: User,
        auth_headers: dict,
        btc_symbol: Symbol,
    ) -> None:
        s = Strategy(
            user_id=other_user.id, name="Other", strategy_type="rsi_ma"
        )
        db_session.add(s)
        db_session.flush()
        v = StrategyVersion(
            strategy_id=s.id, version_number=1, config=VALID_CONFIG, is_active=True
        )
        db_session.add(v)
        db_session.flush()
        run = _create_completed_run(db_session, other_user, v, btc_symbol)

        resp = client.get(f"/api/v1/backtests/{run.id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_nonexistent_run_404(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/backtests/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_invalid_uuid_404(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        resp = client.get("/api/v1/backtests/not-a-uuid", headers=auth_headers)
        assert resp.status_code == 404

    def test_completed_no_equity_returns_minimal_curve(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run(
            db_session,
            test_user,
            v,
            btc_symbol,
            with_equity=False,
            with_trades=False,
        )
        resp = client.get(f"/api/v1/backtests/{run.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["equity_curve"]) == 2


class TestGetBacktestTrades:
    def test_get_trades(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run(db_session, test_user, v, btc_symbol)
        resp = client.get(
            f"/api/v1/backtests/{run.id}/trades", headers=auth_headers
        )
        assert resp.status_code == 200
        trades = resp.json()
        assert len(trades) == 2
        sides = {t["side"] for t in trades}
        assert "buy" in sides
        assert "sell" in sides

    def test_trades_nonexistent_run_404(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/backtests/{fake_id}/trades", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_trades_requires_auth(self, client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/backtests/{fake_id}/trades")
        assert resp.status_code == 401


class TestGetBacktestEquity:
    def test_get_equity(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run(db_session, test_user, v, btc_symbol)
        resp = client.get(
            f"/api/v1/backtests/{run.id}/equity", headers=auth_headers
        )
        assert resp.status_code == 200
        equity = resp.json()
        assert len(equity) == 3
        assert all("timestamp" in e and "equity_value" in e for e in equity)

    def test_equity_completed_no_snapshots_returns_minimal(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run(
            db_session, test_user, v, btc_symbol, with_equity=False, with_trades=False
        )
        resp = client.get(
            f"/api/v1/backtests/{run.id}/equity", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_equity_pending_run_empty(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = BacktestRun(
            user_id=test_user.id,
            strategy_version_id=v.id,
            symbol_id=btc_symbol.id,
            timeframe="1h",
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
            status=BacktestRunStatus.PENDING,
        )
        db_session.add(run)
        db_session.flush()
        resp = client.get(
            f"/api/v1/backtests/{run.id}/equity", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetBacktestMetrics:
    def test_get_metrics(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run(db_session, test_user, v, btc_symbol)
        resp = client.get(
            f"/api/v1/backtests/{run.id}/metrics", headers=auth_headers
        )
        assert resp.status_code == 200
        metrics = resp.json()
        assert "total_return_pct" in metrics
        assert "max_drawdown_pct" in metrics

    def test_metrics_no_metrics_404(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run(
            db_session,
            test_user,
            v,
            btc_symbol,
            with_metrics=False,
            with_equity=False,
            with_trades=False,
        )
        resp = client.get(
            f"/api/v1/backtests/{run.id}/metrics", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_metrics_requires_auth(self, client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/backtests/{fake_id}/metrics")
        assert resp.status_code == 401
