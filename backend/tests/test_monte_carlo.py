"""Unit tests for Monte Carlo service (Phase 14.3)."""

import pytest

from app.services.backtest.monte_carlo import compute_monte_carlo


def test_shuffle_reproducible_with_seed() -> None:
    a = compute_monte_carlo(
        closed_trade_pnls=[100.0, -50.0, 25.0],
        initial_equity=10_000.0,
        num_simulations=100,
        method="shuffle",
        seed=42,
        original_total_return_pct=1.0,
    )
    b = compute_monte_carlo(
        closed_trade_pnls=[100.0, -50.0, 25.0],
        initial_equity=10_000.0,
        num_simulations=100,
        method="shuffle",
        seed=42,
        original_total_return_pct=1.0,
    )
    assert a.mean_final_equity == b.mean_final_equity
    assert a.worst_final_equity == b.worst_final_equity


def test_bootstrap_probabilities_in_range() -> None:
    r = compute_monte_carlo(
        closed_trade_pnls=[10.0, -5.0, 3.0, 2.0],
        initial_equity=10_000.0,
        num_simulations=200,
        method="bootstrap",
        seed=1,
        original_total_return_pct=None,
    )
    assert 0 <= r.probability_profit_pct <= 100
    assert 0 <= r.probability_loss_pct <= 100
    assert r.p5_final_equity <= r.p95_final_equity


def test_raises_too_few_trades() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        compute_monte_carlo(
            closed_trade_pnls=[100.0],
            initial_equity=10_000.0,
            num_simulations=100,
            method="bootstrap",
            seed=0,
            original_total_return_pct=None,
        )


def test_percentile_band_non_empty() -> None:
    r = compute_monte_carlo(
        closed_trade_pnls=[50.0, -20.0, 10.0, 5.0],
        initial_equity=10_000.0,
        num_simulations=50,
        method="bootstrap",
        seed=99,
        original_total_return_pct=0.5,
    )
    assert len(r.percentile_equity_band) >= 2
    assert r.original_total_return_pct == 0.5
