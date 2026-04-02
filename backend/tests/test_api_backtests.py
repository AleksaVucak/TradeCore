"""API tests for backtests endpoints (Phase 11.2)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.backtest_run import BacktestRun, BacktestRunStatus
from app.models.candle import Candle
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


def _create_completed_run_two_closed_pnls(
    db: Session,
    user: User,
    version: StrategyVersion,
    symbol: Symbol,
) -> BacktestRun:
    """Completed run with two closed sells (P&L) for Monte Carlo (Phase 14.3)."""
    run = BacktestRun(
        user_id=user.id,
        strategy_version_id=version.id,
        symbol_id=symbol.id,
        timeframe="1h",
        start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
        status=BacktestRunStatus.COMPLETED,
        run_options={"initial_equity": 10_000.0},
    )
    db.add(run)
    db.flush()
    db.add_all(
        [
            Trade(
                backtest_run_id=run.id,
                timestamp=datetime(2025, 1, 10, tzinfo=timezone.utc),
                side="buy",
                price=40000.0,
                quantity=0.1,
                fee=4.0,
                slippage=0.0,
                pnl=None,
            ),
            Trade(
                backtest_run_id=run.id,
                timestamp=datetime(2025, 1, 11, tzinfo=timezone.utc),
                side="sell",
                price=41000.0,
                quantity=0.1,
                fee=4.1,
                slippage=0.0,
                pnl=90.0,
            ),
            Trade(
                backtest_run_id=run.id,
                timestamp=datetime(2025, 2, 10, tzinfo=timezone.utc),
                side="buy",
                price=41000.0,
                quantity=0.1,
                fee=4.1,
                slippage=0.0,
                pnl=None,
            ),
            Trade(
                backtest_run_id=run.id,
                timestamp=datetime(2025, 2, 20, tzinfo=timezone.utc),
                side="sell",
                price=42000.0,
                quantity=0.1,
                fee=4.2,
                slippage=0.0,
                pnl=75.5,
            ),
        ]
    )
    db.add(
        MetricSnapshot(
            backtest_run_id=run.id,
            metrics={
                "total_return_pct": 2.5,
                "max_drawdown_pct": 1.0,
                "num_trades": 4,
                "final_equity": 10_250.0,
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


class TestGetBacktestRiskMetrics:
    """Phase 12.2: GET /backtests/{id}/risk-metrics."""

    _EXPECTED_KEYS = frozenset(
        {
            "run_id",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "total_return_pct",
            "annualized_return_pct",
            "max_drawdown_pct",
            "avg_drawdown_pct",
            "var_95",
            "var_99",
            "cvar_95",
            "cvar_99",
            "num_trades",
            "win_rate",
            "profit_factor",
            "avg_win",
            "avg_loss",
            "largest_win",
            "largest_loss",
            "avg_trade_pnl",
            "initial_equity",
            "final_equity",
        }
    )

    def test_risk_metrics_completed_run_200(
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
            f"/api/v1/backtests/{run.id}/risk-metrics", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == self._EXPECTED_KEYS
        assert data["run_id"] == str(run.id)
        assert data["num_trades"] == 1
        assert data["initial_equity"] == 10_000.0
        assert data["final_equity"] == 10_191.8

    def test_risk_metrics_completed_no_equity_uses_metrics_fallback(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        """No snapshots: endpoint builds minimal curve from metrics."""
        _, v = strategy_and_version
        run = _create_completed_run(
            db_session,
            test_user,
            v,
            btc_symbol,
            with_equity=False,
            with_trades=False,
        )
        resp = client.get(
            f"/api/v1/backtests/{run.id}/risk-metrics", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["final_equity"] == 10_191.8

    def test_risk_metrics_pending_400(
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
            f"/api/v1/backtests/{run.id}/risk-metrics", headers=auth_headers
        )
        assert resp.status_code == 400
        assert "completed" in resp.json()["detail"].lower()

    def test_risk_metrics_not_found_404(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/backtests/{fake_id}/risk-metrics", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_risk_metrics_other_user_404(
        self,
        client: TestClient,
        db_session: Session,
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
            strategy_id=s.id,
            version_number=1,
            config=VALID_CONFIG,
            is_active=True,
        )
        db_session.add(v)
        db_session.flush()
        run = _create_completed_run(db_session, other_user, v, btc_symbol)
        resp = client.get(
            f"/api/v1/backtests/{run.id}/risk-metrics", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_risk_metrics_requires_auth(self, client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/backtests/{fake_id}/risk-metrics")
        assert resp.status_code == 401


def _create_candles_for_run(
    db: Session, symbol: Symbol, timeframe: str, start: datetime, end: datetime
) -> list[Candle]:
    """Create sample candles for benchmark testing."""
    from datetime import timedelta

    candles = []
    current = start
    price = 40000.0  # Starting price
    while current <= end:
        c = Candle(
            symbol_id=symbol.id,
            timeframe=timeframe,
            timestamp=current,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price * 1.005,  # Small upward drift
            volume=100.0,
        )
        db.add(c)
        candles.append(c)
        price = price * 1.005  # Continue drift
        if timeframe == "1h":
            current += timedelta(hours=1)
        elif timeframe == "4h":
            current += timedelta(hours=4)
        else:
            current += timedelta(days=1)
        if len(candles) >= 100:
            break
    db.flush()
    return candles


def _create_test_symbol(db: Session, symbol: str) -> Symbol:
    row = Symbol(symbol=symbol, base_asset=symbol[:3], quote_asset="USD", is_active=True)
    db.add(row)
    db.flush()
    return row


class TestGetBacktestBenchmark:
    """Phase 12.4: GET /backtests/{id}/benchmark."""

    _EXPECTED_KEYS = frozenset(
        {
            "run_id",
            "equity_curve",
            "initial_equity",
            "final_equity",
            "total_return_pct",
            "strategy_return_pct",
            "alpha_pct",
        }
    )

    def test_benchmark_completed_run_200(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
    ) -> None:
        _, v = strategy_and_version
        benchmark_symbol = _create_test_symbol(db_session, "BNCHBTCA")
        run = _create_completed_run(db_session, test_user, v, benchmark_symbol)
        _create_candles_for_run(
            db_session, benchmark_symbol, run.timeframe, run.start_time, run.end_time
        )
        resp = client.get(
            f"/api/v1/backtests/{run.id}/benchmark", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == self._EXPECTED_KEYS
        assert data["run_id"] == str(run.id)
        assert data["initial_equity"] == 10_000.0
        assert len(data["equity_curve"]) > 0
        assert data["strategy_return_pct"] == 1.92
        assert "alpha_pct" in data

    def test_benchmark_no_candles_empty_curve(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
    ) -> None:
        """No candles: endpoint returns empty curve but still 200."""
        _, v = strategy_and_version
        benchmark_symbol = _create_test_symbol(db_session, "BNCHBTCB")
        run = _create_completed_run(db_session, test_user, v, benchmark_symbol)
        resp = client.get(
            f"/api/v1/backtests/{run.id}/benchmark", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["equity_curve"] == []
        assert data["total_return_pct"] == 0.0
        assert data["alpha_pct"] == 1.92

    def test_benchmark_pending_400(
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
            f"/api/v1/backtests/{run.id}/benchmark", headers=auth_headers
        )
        assert resp.status_code == 400
        assert "completed" in resp.json()["detail"].lower()

    def test_benchmark_not_found_404(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/backtests/{fake_id}/benchmark", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_benchmark_other_user_404(
        self,
        client: TestClient,
        db_session: Session,
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
            strategy_id=s.id,
            version_number=1,
            config=VALID_CONFIG,
            is_active=True,
        )
        db_session.add(v)
        db_session.flush()
        run = _create_completed_run(db_session, other_user, v, btc_symbol)
        resp = client.get(
            f"/api/v1/backtests/{run.id}/benchmark", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_benchmark_requires_auth(self, client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/backtests/{fake_id}/benchmark")
        assert resp.status_code == 401


class TestWalkForwardValidation:
    """Phase 14.1: POST /backtests/walk-forward."""

    def test_walk_forward_success(
        self,
        client: TestClient,
        db_session: Session,
        auth_headers: dict,
        strategy_and_version,
    ) -> None:
        _, version = strategy_and_version
        walk_symbol = _create_test_symbol(db_session, "WLKFBTCA")
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 5,  tzinfo=timezone.utc)
        _create_candles_for_run(db_session, walk_symbol, "1h", start, end)

        resp = client.post(
            "/api/v1/backtests/walk-forward",
            json={
                "strategy_version_id": version.id,
                "symbol_id": walk_symbol.id,
                "timeframe": "1h",
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "end_time": end.isoformat().replace("+00:00", "Z"),
                "initial_equity": 10000,
                "window_bars": 24,
                "step_bars": 12,
            },
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy_version_id"] == version.id
        assert data["symbol_id"] == walk_symbol.id
        assert data["window_bars"] == 24
        assert data["step_bars"] == 12
        assert len(data["windows"]) >= 2
        assert data["summary"]["total_windows"] == len(data["windows"])
        assert data["summary"]["window_bars"] == 24
        assert "avg_total_return_pct" in data["summary"]
        assert all(window["num_candles"] == 24 for window in data["windows"])

    def test_walk_forward_requires_enough_candles(
        self,
        client: TestClient,
        db_session: Session,
        auth_headers: dict,
        strategy_and_version,
    ) -> None:
        _, version = strategy_and_version
        walk_symbol = _create_test_symbol(db_session, "WLKFBTCB")
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
        _create_candles_for_run(db_session, walk_symbol, "1h", start, end)

        resp = client.post(
            "/api/v1/backtests/walk-forward",
            json={
                "strategy_version_id": version.id,
                "symbol_id": walk_symbol.id,
                "timeframe": "1h",
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "end_time": end.isoformat().replace("+00:00", "Z"),
                "initial_equity": 10000,
                "window_bars": 48,
                "step_bars": 12,
            },
            headers=auth_headers,
        )

        assert resp.status_code == 400
        assert "window size" in resp.json()["detail"].lower()

    def test_walk_forward_other_users_version_404(
        self,
        client: TestClient,
        db_session: Session,
        other_user: User,
        auth_headers: dict,
    ) -> None:
        strategy = Strategy(
            user_id=other_user.id,
            name="Other Walk Forward",
            strategy_type="rsi_ma",
        )
        db_session.add(strategy)
        db_session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id,
            version_number=1,
            config=VALID_CONFIG,
            is_active=True,
        )
        db_session.add(version)
        db_session.flush()
        walk_symbol = _create_test_symbol(db_session, "WLKFBTCC")
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 5, tzinfo=timezone.utc)
        _create_candles_for_run(db_session, walk_symbol, "1h", start, end)

        resp = client.post(
            "/api/v1/backtests/walk-forward",
            json={
                "strategy_version_id": version.id,
                "symbol_id": walk_symbol.id,
                "timeframe": "1h",
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "end_time": end.isoformat().replace("+00:00", "Z"),
                "initial_equity": 10000,
                "window_bars": 24,
                "step_bars": 12,
            },
            headers=auth_headers,
        )

        assert resp.status_code == 404

    def test_walk_forward_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/backtests/walk-forward",
            json={
                "strategy_version_id": 1,
                "symbol_id": 1,
                "timeframe": "1h",
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-01-05T00:00:00Z",
                "initial_equity": 10000,
                "window_bars": 24,
                "step_bars": 12,
            },
        )
        assert resp.status_code == 401


class TestMonteCarlo:
    """Phase 14.3: POST /backtests/{id}/monte-carlo."""

    _EXPECTED_KEYS = frozenset(
        {
            "run_id",
            "method",
            "num_simulations",
            "num_closed_trades",
            "initial_equity",
            "seed",
            "mean_final_equity",
            "median_final_equity",
            "p5_final_equity",
            "p95_final_equity",
            "best_final_equity",
            "worst_final_equity",
            "mean_total_return_pct",
            "median_total_return_pct",
            "p5_total_return_pct",
            "p95_total_return_pct",
            "best_total_return_pct",
            "worst_total_return_pct",
            "mean_max_drawdown_pct",
            "median_max_drawdown_pct",
            "p95_max_drawdown_pct",
            "worst_max_drawdown_pct",
            "probability_profit_pct",
            "probability_loss_pct",
            "probability_drawdown_gt_10_pct",
            "original_total_return_pct",
            "percentile_equity_band",
        }
    )

    def test_monte_carlo_completed_200(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run_two_closed_pnls(db_session, test_user, v, btc_symbol)
        resp = client.post(
            f"/api/v1/backtests/{run.id}/monte-carlo",
            json={"num_simulations": 100, "method": "bootstrap", "seed": 7},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == self._EXPECTED_KEYS
        assert data["run_id"] == str(run.id)
        assert data["method"] == "bootstrap"
        assert data["num_simulations"] == 100
        assert data["num_closed_trades"] == 2
        assert data["initial_equity"] == 10_000.0
        assert data["seed"] == 7
        assert data["original_total_return_pct"] == 2.5
        assert len(data["percentile_equity_band"]) >= 2

    def test_monte_carlo_shuffle(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
        strategy_and_version,
        btc_symbol: Symbol,
    ) -> None:
        _, v = strategy_and_version
        run = _create_completed_run_two_closed_pnls(db_session, test_user, v, btc_symbol)
        resp = client.post(
            f"/api/v1/backtests/{run.id}/monte-carlo",
            json={"num_simulations": 80, "method": "shuffle", "seed": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["method"] == "shuffle"

    def test_monte_carlo_too_few_closed_trades_400(
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
        resp = client.post(
            f"/api/v1/backtests/{run.id}/monte-carlo",
            json={"num_simulations": 100},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "2" in resp.json()["detail"] or "closed" in resp.json()["detail"].lower()

    def test_monte_carlo_pending_400(
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
        resp = client.post(
            f"/api/v1/backtests/{run.id}/monte-carlo",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "completed" in resp.json()["detail"].lower()

    def test_monte_carlo_not_found_404(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/backtests/{fake_id}/monte-carlo",
            json={"num_simulations": 100},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_monte_carlo_other_user_404(
        self,
        client: TestClient,
        db_session: Session,
        other_user: User,
        auth_headers: dict,
        btc_symbol: Symbol,
    ) -> None:
        s = Strategy(
            user_id=other_user.id,
            name="Other MC",
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
        run = _create_completed_run_two_closed_pnls(db_session, other_user, v, btc_symbol)
        resp = client.post(
            f"/api/v1/backtests/{run.id}/monte-carlo",
            json={"num_simulations": 50},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_monte_carlo_requires_auth(self, client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/api/v1/backtests/{fake_id}/monte-carlo", json={})
        assert resp.status_code == 401
