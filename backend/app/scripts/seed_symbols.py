from sqlalchemy.orm import Session

from app.models.symbol import Symbol


def seed_symbols(db: Session) -> None:
    """Insert core symbols (BTCUSD, ETHUSD) if they do not exist."""
    symbols = [
        {"symbol": "BTCUSD", "base_asset": "BTC", "quote_asset": "USD"},
        {"symbol": "ETHUSD", "base_asset": "ETH", "quote_asset": "USD"},
    ]

    for data in symbols:
        existing = db.query(Symbol).filter_by(symbol=data["symbol"]).first()
        if existing is None:
            db.add(Symbol(**data))

