from pydantic import BaseModel


class SymbolResponse(BaseModel):
    id: int
    symbol: str
    base_asset: str
    quote_asset: str
    is_active: bool

    class Config:
        from_attributes = True
