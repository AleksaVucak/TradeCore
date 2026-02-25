from datetime import datetime

from pydantic import BaseModel


class StrategyListItem(BaseModel):
    id: int
    name: str
    strategy_type: str
    created_at: datetime

    class Config:
        from_attributes = True
