from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BacktestRunListItem(BaseModel):
    id: UUID
    symbol_id: int
    timeframe: str
    status: str
    start_time: datetime
    end_time: datetime
    created_at: datetime

    class Config:
        from_attributes = True
