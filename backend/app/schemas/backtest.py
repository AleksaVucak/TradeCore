from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
