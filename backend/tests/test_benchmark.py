"""Unit tests for Phase 12.4 benchmark.compute_benchmark."""

from datetime import datetime, timezone

import pytest

from app.services.backtest.benchmark import compute_benchmark


def _ts(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


class TestComputeBenchmark:
    def test_empty_candles_returns_safe_defaults(self) -> None:
        r = compute_benchmark(
            candle_closes=[],
            initial_equity=10_000.0,
            strategy_return_pct=5.0,
        )
        assert r.equity_curve == []
        assert r.initial_equity == 10_000.0
        assert r.final_equity == 10_000.0
        assert r.total_return_pct == 0.0
        assert r.alpha_pct == 5.0  # Strategy - benchmark (0)

    def test_flat_price_zero_return(self) -> None:
        """Price stays constant, so buy-and-hold return is 0%."""
        candles = [
            (_ts(2025, 1, 1), 100.0),
            (_ts(2025, 1, 2), 100.0),
            (_ts(2025, 1, 3), 100.0),
        ]
        r = compute_benchmark(
            candle_closes=candles,
            initial_equity=10_000.0,
            strategy_return_pct=5.0,
        )
        assert len(r.equity_curve) == 3
        assert r.equity_curve[0].equity_value == 10_000.0
        assert r.equity_curve[-1].equity_value == 10_000.0
        assert r.total_return_pct == 0.0
        assert r.alpha_pct == 5.0

    def test_price_doubles_100pct_return(self) -> None:
        """Price doubles from 100 to 200, so benchmark return is 100%."""
        candles = [
            (_ts(2025, 1, 1), 100.0),
            (_ts(2025, 1, 2), 150.0),
            (_ts(2025, 1, 3), 200.0),
        ]
        r = compute_benchmark(
            candle_closes=candles,
            initial_equity=10_000.0,
            strategy_return_pct=50.0,
        )
        assert len(r.equity_curve) == 3
        assert r.equity_curve[0].equity_value == 10_000.0
        assert r.equity_curve[-1].equity_value == 20_000.0
        assert r.total_return_pct == pytest.approx(100.0, rel=0.01)
        assert r.alpha_pct == pytest.approx(-50.0, rel=0.01)  # Strategy underperformed

    def test_price_drops_negative_return(self) -> None:
        """Price drops 50%, so benchmark loses 50%."""
        candles = [
            (_ts(2025, 1, 1), 100.0),
            (_ts(2025, 1, 2), 75.0),
            (_ts(2025, 1, 3), 50.0),
        ]
        r = compute_benchmark(
            candle_closes=candles,
            initial_equity=10_000.0,
            strategy_return_pct=-30.0,
        )
        assert r.equity_curve[-1].equity_value == 5_000.0
        assert r.total_return_pct == pytest.approx(-50.0, rel=0.01)
        assert r.alpha_pct == pytest.approx(20.0, rel=0.01)  # Strategy outperformed (lost less)

    def test_alpha_calculation(self) -> None:
        """Alpha = strategy_return - benchmark_return."""
        candles = [
            (_ts(2025, 1, 1), 100.0),
            (_ts(2025, 1, 2), 110.0),  # 10% gain
        ]
        r = compute_benchmark(
            candle_closes=candles,
            initial_equity=10_000.0,
            strategy_return_pct=15.0,  # Strategy gained 15%
        )
        assert r.total_return_pct == pytest.approx(10.0, rel=0.01)
        assert r.alpha_pct == pytest.approx(5.0, rel=0.01)  # 15% - 10% = 5%
