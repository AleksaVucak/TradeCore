"""Tests for strategy config validation (Phase 5.1 / Phase 11.1)."""

import pytest
from pydantic import ValidationError

from app.schemas.strategy_config import (
    RsiMaConfig,
    get_config_schema,
    validate_strategy_config,
)


# ---------------------------------------------------------------------------
# RsiMaConfig defaults, custom values, round-trip
# ---------------------------------------------------------------------------

class TestRsiMaConfig:
    def test_defaults(self) -> None:
        config = RsiMaConfig()
        assert config.rsi_period == 14
        assert config.rsi_buy_threshold == 30.0
        assert config.rsi_sell_threshold == 70.0
        assert config.ma_period == 20
        assert config.position_size_pct == 1.0
        assert config.fee_rate == 0.001
        assert config.slippage_rate == 0.0005
        assert config.stop_loss_pct == 2.0
        assert config.take_profit_pct == 5.0

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

    def test_to_config_dict_roundtrip(self) -> None:
        config = RsiMaConfig(rsi_period=10, position_size_pct=0.25)
        data = config.to_config_dict()
        config2 = RsiMaConfig.model_validate(data)
        assert config2.rsi_period == config.rsi_period
        assert config2.position_size_pct == config.position_size_pct

    def test_to_config_dict_has_all_fields(self) -> None:
        config = RsiMaConfig()
        data = config.to_config_dict()
        expected_fields = {
            "rsi_period", "rsi_buy_threshold", "rsi_sell_threshold",
            "ma_period", "position_size_pct", "stop_loss_pct",
            "take_profit_pct", "fee_rate", "slippage_rate",
        }
        assert expected_fields.issubset(data.keys())


# ---------------------------------------------------------------------------
# Validation: RSI thresholds
# ---------------------------------------------------------------------------

class TestRsiThresholdValidation:
    def test_sell_below_buy_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            RsiMaConfig(rsi_buy_threshold=70.0, rsi_sell_threshold=30.0)
        assert "rsi_sell_threshold" in str(exc_info.value)

    def test_sell_equal_buy_allowed(self) -> None:
        config = RsiMaConfig(rsi_buy_threshold=50.0, rsi_sell_threshold=50.0)
        assert config.rsi_buy_threshold == 50.0
        assert config.rsi_sell_threshold == 50.0

    def test_zero_zero_thresholds(self) -> None:
        config = RsiMaConfig(rsi_buy_threshold=0.0, rsi_sell_threshold=0.0)
        assert config.rsi_buy_threshold == 0.0

    def test_hundred_hundred_thresholds(self) -> None:
        config = RsiMaConfig(rsi_buy_threshold=100.0, rsi_sell_threshold=100.0)
        assert config.rsi_sell_threshold == 100.0

    def test_buy_above_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(rsi_buy_threshold=101.0)

    def test_buy_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(rsi_buy_threshold=-1.0)


# ---------------------------------------------------------------------------
# Validation: bounds on numeric fields
# ---------------------------------------------------------------------------

class TestBoundsValidation:
    def test_rsi_period_too_low(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(rsi_period=1)

    def test_rsi_period_too_high(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(rsi_period=101)

    def test_rsi_period_min_max(self) -> None:
        low = RsiMaConfig(rsi_period=2)
        assert low.rsi_period == 2
        high = RsiMaConfig(rsi_period=100)
        assert high.rsi_period == 100

    def test_ma_period_min(self) -> None:
        config = RsiMaConfig(ma_period=1)
        assert config.ma_period == 1

    def test_ma_period_max(self) -> None:
        config = RsiMaConfig(ma_period=500)
        assert config.ma_period == 500

    def test_ma_period_too_high(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(ma_period=501)

    def test_position_size_too_low(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(position_size_pct=0.0)

    def test_position_size_too_high(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(position_size_pct=1.5)

    def test_position_size_min(self) -> None:
        config = RsiMaConfig(position_size_pct=0.01)
        assert config.position_size_pct == 0.01

    def test_stop_loss_zero(self) -> None:
        config = RsiMaConfig(stop_loss_pct=0.0)
        assert config.stop_loss_pct == 0.0

    def test_stop_loss_100(self) -> None:
        config = RsiMaConfig(stop_loss_pct=100.0)
        assert config.stop_loss_pct == 100.0

    def test_take_profit_zero(self) -> None:
        config = RsiMaConfig(take_profit_pct=0.0)
        assert config.take_profit_pct == 0.0

    def test_fee_rate_zero(self) -> None:
        config = RsiMaConfig(fee_rate=0.0)
        assert config.fee_rate == 0.0

    def test_fee_rate_too_high(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(fee_rate=1.0)

    def test_slippage_rate_zero(self) -> None:
        config = RsiMaConfig(slippage_rate=0.0)
        assert config.slippage_rate == 0.0

    def test_slippage_rate_too_high(self) -> None:
        with pytest.raises(ValidationError):
            RsiMaConfig(slippage_rate=1.0)


# ---------------------------------------------------------------------------
# Aggressive / extreme config combinations
# ---------------------------------------------------------------------------

class TestAggressiveConfigs:
    def test_very_tight_sl_tp(self) -> None:
        """Extremely tight SL/TP should still produce a valid config."""
        config = RsiMaConfig(stop_loss_pct=0.01, take_profit_pct=0.01)
        assert config.stop_loss_pct == 0.01
        assert config.take_profit_pct == 0.01

    def test_tiny_position_size(self) -> None:
        config = RsiMaConfig(position_size_pct=0.01)
        assert config.position_size_pct == 0.01

    def test_high_fee_high_slippage(self) -> None:
        config = RsiMaConfig(fee_rate=0.99, slippage_rate=0.99)
        assert config.fee_rate == 0.99
        assert config.slippage_rate == 0.99


# ---------------------------------------------------------------------------
# validate_strategy_config helper
# ---------------------------------------------------------------------------

class TestValidateStrategyConfig:
    def test_rsi_ma_valid(self) -> None:
        config = validate_strategy_config(
            "rsi_ma",
            {"rsi_period": 14, "rsi_buy_threshold": 30, "rsi_sell_threshold": 70},
        )
        assert isinstance(config, RsiMaConfig)
        assert config.rsi_period == 14

    def test_rsi_ma_with_defaults(self) -> None:
        config = validate_strategy_config("rsi_ma", {})
        assert isinstance(config, RsiMaConfig)
        assert config.rsi_period == 14

    def test_rsi_ma_invalid_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_strategy_config("rsi_ma", {"rsi_period": -1})

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy_type"):
            validate_strategy_config("unknown", {})

    def test_empty_string_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy_type"):
            validate_strategy_config("", {})


# ---------------------------------------------------------------------------
# get_config_schema helper
# ---------------------------------------------------------------------------

class TestGetConfigSchema:
    def test_rsi_ma_returns_model_class(self) -> None:
        schema = get_config_schema("rsi_ma")
        assert schema is RsiMaConfig

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy_type"):
            get_config_schema("unknown")
