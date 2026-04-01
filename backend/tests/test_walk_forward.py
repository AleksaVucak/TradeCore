from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.strategy_config import RsiMaConfig
from app.services.backtest.types import BacktestCandle
from app.services.backtest.walk_forward import run_walk_forward_validation


def _build_candles(count: int) -> list[BacktestCandle]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    candles: list[BacktestCandle] = []
    for index in range(count):
        close = price + (0.8 if index % 3 == 0 else -0.2 if index % 5 == 0 else 0.4)
        candles.append(
            BacktestCandle(
                timestamp=start + timedelta(hours=index),
                open=price,
                high=max(price, close) + 0.5,
                low=min(price, close) - 0.5,
                close=close,
                volume=1000.0 + index,
            )
        )
        price = close
    return candles


def test_walk_forward_returns_multiple_windows() -> None:
    result = run_walk_forward_validation(
        _build_candles(30),
        RsiMaConfig(),
        initial_equity=10_000.0,
        window_bars=10,
        step_bars=5,
        period_hours=1.0,
    )

    assert len(result.windows) == 5
    assert result.summary.total_windows == 5
    assert result.summary.window_bars == 10
    assert result.summary.step_bars == 5
    assert all(window.num_candles == 10 for window in result.windows)


def test_walk_forward_raises_when_window_too_large() -> None:
    with pytest.raises(ValueError, match="window size"):
        run_walk_forward_validation(
            _build_candles(8),
            RsiMaConfig(),
            initial_equity=10_000.0,
            window_bars=10,
            step_bars=1,
            period_hours=1.0,
        )
