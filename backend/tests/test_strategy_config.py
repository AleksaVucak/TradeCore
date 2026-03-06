"""Tests for strategy config validation (Phase 5.1)."""

import pytest
from pydantic import ValidationError

from app.schemas.strategy_config import (
    RsiMaConfig,
    get_config_schema,
    validate_strategy_config,
)


class TestRsiMaConfig:
    def test_defaults(self) -> None:
        config = RsiMaConfig()
        assert config.rsi_period == 14
        assert config.rsi_buy_threshold == 30.0
        assert config.rsi_sell_threshold == 70.0
        assert config.ma_period == 20
        assert config.position_size_pct == 1.0
        assert config.fee_rate == 0.001

    def test_custom_values(self) -> None:
        config = RsiMaConfig(
            rsi_period=7,
            rsi_buy_threshold=25.0,
            rsi_sell_threshold=75.0,
            position_size_pct=0.5,
            stop_loss_pct=1.5,
            take_profit_pct=3.0,
            fee_rate=0.002,
            slippage_rate=0.001,
        )
        assert config.rsi_period == 7
        assert config.position_size_pct == 0.5
        assert config.to_config_dict()["rsi_period"] == 7

    def test_sell_below_buy_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            RsiMaConfig(rsi_buy_threshold=70.0, rsi_sell_threshold=30.0)
        assert "rsi_sell_threshold" in str(exc_info.value)

    def test_sell_equal_buy_allowed(self) -> None:
        """50/50 is valid: buy when RSI < 50, sell when RSI > 50."""
        config = RsiMaConfig(rsi_buy_threshold=50.0, rsi_sell_threshold=50.0)
        assert config.rsi_buy_threshold == 50.0
        assert config.rsi_sell_threshold == 50.0

    def test_bounds_rsi_period(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(rsi_period=1)
        with pytest.raises(ValidationError):
            RsiMaConfig(rsi_period=101)

    def test_bounds_position_size(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(position_size_pct=0.0)
        with pytest.raises(ValidationError):
            RsiMaConfig(position_size_pct=1.5)

    def test_to_config_dict_roundtrip(self) -> None:
        config = RsiMaConfig(rsi_period=10, position_size_pct=0.25)
        data = config.to_config_dict()
        config2 = RsiMaConfig.model_validate(data)
        assert config2.rsi_period == config.rsi_period
        assert config2.position_size_pct == config.position_size_pct


class TestValidateStrategyConfig:
    def test_rsi_ma_valid(self) -> None:
        config = validate_strategy_config(
            "rsi_ma",
            {"rsi_period": 14, "rsi_buy_threshold": 30, "rsi_sell_threshold": 70},
        )
        assert isinstance(config, RsiMaConfig)
        assert config.rsi_period == 14

    def test_rsi_ma_invalid_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_strategy_config("rsi_ma", {"rsi_period": -1})

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy_type"):
            validate_strategy_config("unknown", {})


class TestGetConfigSchema:
    def test_rsi_ma_returns_model_class(self) -> None:
        schema = get_config_schema("rsi_ma")
        assert schema is RsiMaConfig

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy_type"):
            get_config_schema("unknown")
