"""
Strategy config validation.

Validated Pydantic models for strategy parameters. StrategyVersion.config (JSONB)
must match one of these schemas based on strategy_type.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Supported strategy types
# ---------------------------------------------------------------------------
StrategyType = Literal["rsi_ma", "ml_signal"]

# ---------------------------------------------------------------------------
# Feature catalogue — canonical names the ML pipeline can compute
# ---------------------------------------------------------------------------
ML_FEATURE_CATALOG: list[str] = [
    "rsi_14",
    "rsi_7",
    "sma_20",
    "sma_50",
    "ema_12",
    "ema_26",
    "macd",
    "macd_signal",
    "macd_hist",
    "bbands_upper",
    "bbands_lower",
    "bbands_width",
    "atr_14",
    "obv",
    "vwap",
    "log_return_1",
    "log_return_5",
    "volatility_20",
]

# ---------------------------------------------------------------------------
# Sentiment filter sub-config (Phase 17.3)
# ---------------------------------------------------------------------------

SentimentFilterMode = Literal["block_negative", "require_positive", "threshold"]


class SentimentFilterConfig(BaseModel):
    """Optional sentiment gate applied to strategy entries (Phase 17.3).

    When attached to a strategy config, the backtest engine evaluates the
    aggregate sentiment for the trading symbol over the configured lookback
    window **using only sentiment data published strictly before the current
    candle's timestamp** (no look-ahead).  The decision can:

    * **block_negative** — block new long entries while aggregate score is
      strictly below ``min_score`` (default 0).
    * **require_positive** — only allow new long entries while aggregate score
      is strictly above ``min_score`` (default 0).
    * **threshold** — only allow new long entries while aggregate score is
      within ``[min_score, max_score]``.

    Exits (stop-loss, take-profit, strategy-defined sell signals) are never
    gated; risk management always takes precedence over sentiment.
    """

    enabled: bool = Field(True, description="Master switch for this filter")
    mode: SentimentFilterMode = Field(
        "block_negative",
        description="How aggregate sentiment is interpreted into a trading gate",
    )
    lookback_hours: int = Field(
        24, ge=1, le=720,
        description="How far back to aggregate sentiment when evaluating each bar",
    )
    min_score: float = Field(
        0.0, ge=-1.0, le=1.0,
        description="Lower bound for allowed aggregate score (mode-dependent)",
    )
    max_score: float = Field(
        1.0, ge=-1.0, le=1.0,
        description="Upper bound (only used by 'threshold' mode)",
    )
    min_samples: int = Field(
        1, ge=1, le=1000,
        description="Minimum number of sentiment rows required inside the window",
    )
    allow_when_missing: bool = Field(
        True,
        description=(
            "If the window has fewer than min_samples rows, allow trades when True "
            "(fail-open) or block them when False (fail-closed)."
        ),
    )

    @model_validator(mode="after")
    def _validate_threshold_bounds(self) -> "SentimentFilterConfig":
        if self.mode == "threshold" and self.max_score < self.min_score:
            raise ValueError(
                "max_score must be >= min_score for sentiment_filter mode='threshold' "
                f"(got min={self.min_score}, max={self.max_score})"
            )
        return self


# ---------------------------------------------------------------------------
# RSI + MA config
# ---------------------------------------------------------------------------


class RsiMaConfig(BaseModel):
    """
    Config for RSI + moving average filter strategy.

    Buy when RSI < rsi_buy_threshold and price above MA; sell when RSI > rsi_sell_threshold
    or stop loss / take profit hit.
    """

    rsi_period: int = Field(14, ge=2, le=100, description="RSI period")
    rsi_buy_threshold: float = Field(30.0, ge=0.0, le=100.0, description="Buy when RSI below this")
    rsi_sell_threshold: float = Field(70.0, ge=0.0, le=100.0, description="Sell when RSI above this")

    ma_period: int = Field(20, ge=1, le=500, description="MA period for trend filter")

    position_size_pct: float = Field(
        1.0, ge=0.01, le=1.0, description="Position size as fraction of equity (0.01 = 1%)"
    )
    stop_loss_pct: float = Field(2.0, ge=0.0, le=100.0, description="Stop loss % from entry")
    take_profit_pct: float = Field(5.0, ge=0.0, le=100.0, description="Take profit % from entry")

    fee_rate: float = Field(0.001, ge=0.0, lt=1.0, description="Fee per trade (0.001 = 0.1%)")
    slippage_rate: float = Field(0.0005, ge=0.0, lt=1.0, description="Slippage assumption (0.0005 = 0.05%)")

    sentiment_filter: SentimentFilterConfig | None = Field(
        default=None,
        description="Optional sentiment gate on new long entries (Phase 17.3)",
    )

    @model_validator(mode="after")
    def sell_at_least_buy(self) -> "RsiMaConfig":
        if self.rsi_sell_threshold < self.rsi_buy_threshold:
            raise ValueError("rsi_sell_threshold must be >= rsi_buy_threshold")
        return self

    def to_config_dict(self) -> dict[str, Any]:
        """Return dict suitable for JSONB storage (StrategyVersion.config)."""
        return self.model_dump()


# ---------------------------------------------------------------------------
# ML Signal config
# ---------------------------------------------------------------------------


class MlSignalConfig(BaseModel):
    """
    Config for an ML-driven signal strategy.

    The model produces a probability of upward movement at each bar.
    - Enter LONG when probability >= long_threshold.
    - Exit (or go flat) when probability <= exit_threshold.
    """

    model_id: int = Field(..., description="ID of a trained MLModelMetadata row to use for inference")

    features: list[str] = Field(
        default_factory=lambda: ["rsi_14", "sma_20", "macd", "bbands_width", "atr_14", "log_return_1"],
        min_length=1,
        description="Feature names the model was trained on (must match training features)",
    )

    long_threshold: float = Field(
        0.55, ge=0.0, le=1.0,
        description="Enter long when predicted probability >= this value",
    )
    exit_threshold: float = Field(
        0.45, ge=0.0, le=1.0,
        description="Exit position when predicted probability <= this value",
    )

    position_size_pct: float = Field(
        1.0, ge=0.01, le=1.0,
        description="Position size as fraction of equity (0.01 = 1%)",
    )
    stop_loss_pct: float = Field(
        3.0, ge=0.0, le=100.0,
        description="Stop loss % from entry",
    )
    take_profit_pct: float = Field(
        6.0, ge=0.0, le=100.0,
        description="Take profit % from entry",
    )

    fee_rate: float = Field(0.001, ge=0.0, lt=1.0, description="Fee per trade (0.001 = 0.1%)")
    slippage_rate: float = Field(0.0005, ge=0.0, lt=1.0, description="Slippage assumption (0.0005 = 0.05%)")

    sentiment_filter: SentimentFilterConfig | None = Field(
        default=None,
        description="Optional sentiment gate on new long entries (Phase 17.3)",
    )

    @model_validator(mode="after")
    def thresholds_ordered(self) -> "MlSignalConfig":
        if self.exit_threshold >= self.long_threshold:
            raise ValueError(
                "exit_threshold must be strictly less than long_threshold "
                f"(got exit={self.exit_threshold}, long={self.long_threshold})"
            )
        return self

    @model_validator(mode="after")
    def features_in_catalog(self) -> "MlSignalConfig":
        unknown = set(self.features) - set(ML_FEATURE_CATALOG)
        if unknown:
            raise ValueError(
                f"Unknown features: {sorted(unknown)}. "
                f"Allowed: {ML_FEATURE_CATALOG}"
            )
        return self

    def to_config_dict(self) -> dict[str, Any]:
        """Return dict suitable for JSONB storage (StrategyVersion.config)."""
        return self.model_dump()


# ---------------------------------------------------------------------------
# Dispatch helpers
# ---------------------------------------------------------------------------

_STRATEGY_REGISTRY: dict[str, type[BaseModel]] = {
    "rsi_ma": RsiMaConfig,
    "ml_signal": MlSignalConfig,
}


def validate_strategy_config(strategy_type: str, config: dict[str, Any]) -> BaseModel:
    """
    Validate config dict for the given strategy_type. Returns the validated Pydantic model.

    Raises ValueError if strategy_type is unknown or config is invalid.
    """
    model_cls = _STRATEGY_REGISTRY.get(strategy_type)
    if model_cls is None:
        supported = ", ".join(sorted(_STRATEGY_REGISTRY))
        raise ValueError(f"Unknown strategy_type: {strategy_type}. Supported: {supported}")
    return model_cls.model_validate(config)


def get_config_schema(strategy_type: str) -> type[BaseModel]:
    """Return the Pydantic model class for a strategy type (for OpenAPI/docs)."""
    model_cls = _STRATEGY_REGISTRY.get(strategy_type)
    if model_cls is None:
        supported = ", ".join(sorted(_STRATEGY_REGISTRY))
        raise ValueError(f"Unknown strategy_type: {strategy_type}. Supported: {supported}")
    return model_cls
