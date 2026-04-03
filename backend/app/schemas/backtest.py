from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TradeOut(BaseModel):
    """Single trade from a completed backtest run (Phase 7.2)."""

    id: UUID
    timestamp: datetime
    side: str
    price: float
    quantity: float
    fee: float = 0.0
    slippage: float = 0.0
    pnl: float | None = None

    class Config:
        from_attributes = True


class EquityPointOut(BaseModel):
    """One point on the equity curve (Phase 7.2)."""

    timestamp: datetime
    equity_value: float

    class Config:
        from_attributes = True


class BacktestRunListItem(BaseModel):
    """List item for run history table (Phase 8.1)."""

    id: UUID
    symbol_id: int
    symbol_name: str | None = None  # e.g. BTC (Phase 8.1)
    strategy_name: str | None = None  # e.g. My Strategy (Phase 8.1)
    timeframe: str
    status: str
    start_time: datetime
    end_time: datetime
    created_at: datetime
    error_message: str | None = None  # Set when status is failed (Phase 7.3)
    total_return_pct: float | None = None  # From metrics when completed (Phase 8.1)
    max_drawdown_pct: float | None = None  # From metrics when completed (Phase 8.1)

    class Config:
        from_attributes = True


class CreateBacktestRequest(BaseModel):
    strategy_version_id: int = Field(..., description="Strategy version to run")
    symbol_id: int = Field(..., description="Symbol (e.g. BTC)")
    timeframe: str = Field(..., description="Candle interval: 1h or 4h")
    start_time: datetime = Field(..., description="Backtest start (UTC)")
    end_time: datetime = Field(..., description="Backtest end (UTC)")
    initial_equity: float = Field(10_000.0, ge=0.01, description="Starting equity")

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        allowed = {"1h", "4h", "1d"}
        if value not in allowed:
            raise ValueError(f"timeframe must be one of: {', '.join(sorted(allowed))}")
        return value


class WalkForwardValidationRequest(BaseModel):
    strategy_version_id: int = Field(..., description="Strategy version to validate")
    symbol_id: int = Field(..., description="Symbol to validate on")
    timeframe: str = Field(..., description="Candle interval: 1h, 4h, or 1d")
    start_time: datetime = Field(..., description="Validation start (UTC)")
    end_time: datetime = Field(..., description="Validation end (UTC)")
    initial_equity: float = Field(10_000.0, ge=0.01, description="Starting equity per window")
    window_bars: int = Field(..., ge=2, description="Bars included in each walk-forward window")
    step_bars: int = Field(..., ge=1, description="Bars to move forward between windows")

    @field_validator("timeframe")
    @classmethod
    def validate_walk_forward_timeframe(cls, value: str) -> str:
        allowed = {"1h", "4h", "1d"}
        if value not in allowed:
            raise ValueError(f"timeframe must be one of: {', '.join(sorted(allowed))}")
        return value


class WalkForwardWindowOut(BaseModel):
    window_index: int
    start_time: datetime
    end_time: datetime
    num_candles: int
    num_trades: int
    initial_equity: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float


class WalkForwardSummaryOut(BaseModel):
    total_windows: int
    window_bars: int
    step_bars: int
    profitable_windows: int
    profitable_window_pct: float
    avg_total_return_pct: float
    best_total_return_pct: float
    worst_total_return_pct: float
    avg_max_drawdown_pct: float
    avg_sharpe_ratio: float


class WalkForwardValidationResponse(BaseModel):
    strategy_version_id: int
    symbol_id: int
    timeframe: str
    start_time: datetime
    end_time: datetime
    initial_equity: float
    window_bars: int
    step_bars: int
    windows: list[WalkForwardWindowOut]
    summary: WalkForwardSummaryOut


class BacktestRunDetail(BaseModel):
    id: UUID
    symbol_id: int
    timeframe: str
    status: str
    start_time: datetime
    end_time: datetime
    created_at: datetime
    error_message: str | None = None
    trades: list[TradeOut] = Field(default_factory=list, description="Trades (when run completed)")
    equity_curve: list[EquityPointOut] = Field(
        default_factory=list, description="Equity curve (when run completed)"
    )
    metrics: dict | None = Field(default=None, description="Metrics snapshot (when run completed)")

    class Config:
        from_attributes = True


class BenchmarkPointOut(BaseModel):
    """One point on the buy-and-hold benchmark equity curve (Phase 12.4)."""

    timestamp: datetime
    equity_value: float


class BenchmarkResponse(BaseModel):
    """Buy-and-hold benchmark comparison for a completed backtest run (Phase 12.4)."""

    run_id: UUID
    equity_curve: list[BenchmarkPointOut] = Field(
        ..., description="Buy-and-hold equity curve over the backtest period"
    )
    initial_equity: float = Field(..., description="Starting equity")
    final_equity: float = Field(..., description="Ending equity (buy-and-hold)")
    total_return_pct: float = Field(..., description="Buy-and-hold total return %")
    strategy_return_pct: float = Field(..., description="Strategy total return %")
    alpha_pct: float = Field(
        ..., description="Alpha: strategy return - benchmark return (percentage points)"
    )


class RiskMetricsResponse(BaseModel):
    """Advanced risk metrics for a completed backtest run (Phase 12.2)."""

    run_id: UUID

    # Risk-adjusted returns
    sharpe_ratio: float = Field(..., description="Sharpe ratio (annualized)")
    sortino_ratio: float = Field(..., description="Sortino ratio (only penalizes downside)")
    calmar_ratio: float = Field(..., description="Calmar ratio (annualized return / max drawdown)")

    # Return metrics
    total_return_pct: float = Field(..., description="Total return as percentage")
    annualized_return_pct: float = Field(..., description="Annualized return as percentage")

    # Drawdown metrics
    max_drawdown_pct: float = Field(..., description="Maximum drawdown as percentage")
    avg_drawdown_pct: float = Field(..., description="Average drawdown as percentage")

    # Value at Risk (negative values indicate potential loss)
    var_95: float = Field(..., description="95% Value at Risk (daily return percentile)")
    var_99: float = Field(..., description="99% Value at Risk (daily return percentile)")
    cvar_95: float = Field(..., description="95% Conditional VaR (Expected Shortfall)")
    cvar_99: float = Field(..., description="99% Conditional VaR (Expected Shortfall)")

    # Trade statistics
    num_trades: int = Field(..., description="Number of closed trades")
    win_rate: float = Field(..., description="Win rate as percentage")
    profit_factor: float = Field(..., description="Gross profit / gross loss")
    avg_win: float = Field(..., description="Average winning trade P&L")
    avg_loss: float = Field(..., description="Average losing trade P&L")
    largest_win: float = Field(..., description="Largest single winning trade")
    largest_loss: float = Field(..., description="Largest single losing trade (negative)")
    avg_trade_pnl: float = Field(..., description="Average P&L per trade")

    # Equity
    initial_equity: float = Field(..., description="Starting equity")
    final_equity: float = Field(..., description="Ending equity")


class MonteCarloRequest(BaseModel):
    """Optional parameters for POST /backtests/{id}/monte-carlo (Phase 14.3)."""

    num_simulations: int = Field(
        500,
        ge=50,
        le=10_000,
        description="Number of simulated paths",
    )
    method: Literal["bootstrap", "shuffle"] = Field(
        "bootstrap",
        description="bootstrap: resample trades with replacement; shuffle: random order",
    )
    seed: int | None = Field(
        None,
        description="Optional RNG seed for reproducible results",
    )


class MonteCarloPercentilePointOut(BaseModel):
    step_index: int = Field(..., description="Trade step (0 = initial equity)")
    p5_equity: float
    p50_equity: float
    p95_equity: float


class MonteCarloHistogramBinOut(BaseModel):
    """One histogram bin for simulated outcomes (Phase 14.4)."""

    bin_start: float = Field(..., description="Inclusive bin lower edge")
    bin_end: float = Field(..., description="Upper edge (last bin includes max)")
    count: int = Field(..., ge=0, description="Number of simulations in this bin")


class MonteCarloConfidenceIntervalsOut(BaseModel):
    """Central percentile intervals (not parametric CI); P5–P95 ≈ 90%, P2.5–P97.5 ≈ 95%."""

    return_pct_ci_90_low: float
    return_pct_ci_90_high: float
    return_pct_ci_95_low: float
    return_pct_ci_95_high: float
    final_equity_ci_90_low: float
    final_equity_ci_90_high: float
    final_equity_ci_95_low: float
    final_equity_ci_95_high: float


class MonteCarloResponse(BaseModel):
    """Monte Carlo robustness summary for a completed backtest (Phase 14.3–14.4)."""

    run_id: UUID
    method: Literal["bootstrap", "shuffle"]
    num_simulations: int
    num_closed_trades: int
    initial_equity: float
    seed: int | None = None

    mean_final_equity: float
    median_final_equity: float
    p5_final_equity: float
    p95_final_equity: float
    best_final_equity: float
    worst_final_equity: float

    mean_total_return_pct: float
    median_total_return_pct: float
    p5_total_return_pct: float
    p95_total_return_pct: float
    best_total_return_pct: float
    worst_total_return_pct: float

    mean_max_drawdown_pct: float
    median_max_drawdown_pct: float
    p95_max_drawdown_pct: float
    worst_max_drawdown_pct: float

    probability_profit_pct: float = Field(
        ...,
        description="Percent of simulations ending above initial equity",
    )
    probability_loss_pct: float = Field(
        ...,
        description="Percent of simulations ending below initial equity",
    )
    probability_drawdown_gt_10_pct: float = Field(
        ...,
        description="Percent of simulations with max drawdown over 10%",
    )

    original_total_return_pct: float | None = Field(
        None,
        description="Actual run total return % from metrics (if available)",
    )
    percentile_equity_band: list[MonteCarloPercentilePointOut] = Field(
        default_factory=list,
        description="P5/P50/P95 equity at each step (subsampled if many trades)",
    )
    histogram_return_pct: list[MonteCarloHistogramBinOut] = Field(
        default_factory=list,
        description="Histogram of simulated total return % across runs",
    )
    histogram_final_equity: list[MonteCarloHistogramBinOut] = Field(
        default_factory=list,
        description="Histogram of simulated final equity across runs",
    )
    confidence_intervals: MonteCarloConfidenceIntervalsOut = Field(
        ...,
        description="Central interval estimates from simulation percentiles",
    )
