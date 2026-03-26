"""Unit tests for Phase 12.2 risk_metrics.compute_risk_metrics."""

from datetime import datetime, timezone

import pytest

from app.services.backtest.risk_metrics import compute_risk_metrics


def _ts(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


class TestComputeRiskMetrics:
    def test_empty_equity_returns_safe_defaults(self) -> None:
        r = compute_risk_metrics(
            equity_values=[],
            equity_timestamps=[],
            trade_pnls=[],
            initial_equity=10_000.0,
        )
        d = r.to_dict()
        assert d["sharpe_ratio"] == 0.0
        assert d["sortino_ratio"] == 0.0
        assert d["num_trades"] == 0
        assert d["initial_equity"] == 10_000.0
        assert d["final_equity"] == 10_000.0

    def test_simple_upward_curve_positive_total_return(self) -> None:
        ts = [_ts(2025, 1, 1), _ts(2025, 6, 1)]
        r = compute_risk_metrics(
            equity_values=[10_000.0, 11_000.0],
            equity_timestamps=ts,
            trade_pnls=[500.0],
            initial_equity=10_000.0,
            period_hours=1.0,
        )
        assert r.total_return_pct == pytest.approx(10.0, rel=0.01)
        assert r.final_equity == 11_000.0
        assert r.num_trades == 1
        assert r.win_rate == 100.0

    def test_trade_stats_from_pnls(self) -> None:
        ts = [_ts(2025, 1, 1), _ts(2025, 6, 1)]
        r = compute_risk_metrics(
            equity_values=[10_000.0, 10_200.0],
            equity_timestamps=ts,
            trade_pnls=[100.0, -50.0, 150.0],
            initial_equity=10_000.0,
            period_hours=24.0,
        )
        assert r.num_trades == 3
        assert r.win_rate == pytest.approx(100 * 2 / 3, rel=0.01)
        assert r.largest_win == 150.0
        assert r.largest_loss == -50.0
