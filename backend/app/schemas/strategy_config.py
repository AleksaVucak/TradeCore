"""
Strategy config validation (Phase 5.1).

Validated Pydantic models for strategy parameters. StrategyVersion.config (JSONB)
must match one of these schemas based on strategy_type.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# Supported strategy types; add new literals and config models as needed.
StrategyType = Literal["rsi_ma"]


class RsiMaConfig(BaseModel):
    """
    Config for RSI + moving average filter strategy.

    Buy when RSI < rsi_buy_threshold and price above MA; sell when RSI > rsi_sell_threshold
    or stop loss / take profit hit.
    """

    # RSI
    rsi_period: int = Field(14, ge=2, le=100, description="RSI period")
    rsi_buy_threshold: float = Field(30.0, ge=0.0, le=100.0, description="Buy when RSI below this")
    rsi_sell_threshold: float = Field(70.0, ge=0.0, le=100.0, description="Sell when RSI above this")

    # Moving average filter
    ma_period: int = Field(20, ge=1, le=500, description="MA period for trend filter")

    # Position & risk
    position_size_pct: float = Field(
        1.0, ge=0.01, le=1.0, description="Position size as fraction of equity (0.01 = 1%)"
    )
    stop_loss_pct: float = Field(2.0, ge=0.0, le=100.0, description="Stop loss % from entry")
    take_profit_pct: float = Field(5.0, ge=0.0, le=100.0, description="Take profit % from entry")

    # Execution
    fee_rate: float = Field(0.001, ge=0.0, lt=1.0, description="Fee per trade (0.001 = 0.1%)")
    slippage_rate: float = Field(0.0005, ge=0.0, lt=1.0, description="Slippage assumption (0.0005 = 0.05%)")

    @model_validator(mode="after")
    def sell_at_least_buy(self) -> "RsiMaConfig":
        if self.rsi_sell_threshold < self.rsi_buy_threshold:
            raise ValueError("rsi_sell_threshold must be >= rsi_buy_threshold")
        return self

    def to_config_dict(self) -> dict[str, Any]:
        """Return dict suitable for JSONB storage (StrategyVersion.config)."""
        return self.model_dump()


def validate_strategy_config(strategy_type: str, config: dict[str, Any]) -> BaseModel:
    """
    Validate config dict for the given strategy_type. Returns the validated Pydantic model.

    Raises ValueError if strategy_type is unknown or config is invalid.
    """
    if strategy_type == "rsi_ma":
        return RsiMaConfig.model_validate(config)
    raise ValueError(f"Unknown strategy_type: {strategy_type}. Supported: rsi_ma")


def get_config_schema(strategy_type: str) -> type[BaseModel]:
    """Return the Pydantic model class for a strategy type (for OpenAPI/docs)."""
    if strategy_type == "rsi_ma":
        return RsiMaConfig
    raise ValueError(f"Unknown strategy_type: {strategy_type}")
