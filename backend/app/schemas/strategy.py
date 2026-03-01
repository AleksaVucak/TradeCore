from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.strategy_config import StrategyType


class StrategyListItem(BaseModel):
    id: int
    name: str
    strategy_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class StrategyVersionResponse(BaseModel):
    id: int
    version_number: int
    config: dict[str, Any]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class StrategyDetail(BaseModel):
    id: int
    name: str
    description: str | None
    strategy_type: str
    created_at: datetime
    updated_at: datetime
    versions: list[StrategyVersionResponse]

    class Config:
        from_attributes = True


class CreateStrategyRequest(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=500)
    strategy_type: StrategyType
    config: dict[str, Any]


class UpdateStrategyRequest(BaseModel):
    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=500)


class CreateStrategyVersionRequest(BaseModel):
    config: dict[str, Any]
