"""seed default trading symbols (BTCUSD, ETHUSD)

Revision ID: c5a8f2d7e9b1
Revises: b3f7d9e1a4c8
Create Date: 2026-04-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5a8f2d7e9b1"
down_revision: Union[str, Sequence[str], None] = "b3f7d9e1a4c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SYMBOLS = [
    {"symbol": "BTCUSD", "base_asset": "BTC", "quote_asset": "USD"},
    {"symbol": "ETHUSD", "base_asset": "ETH", "quote_asset": "USD"},
]


def upgrade() -> None:
    symbols_table = sa.table(
        "symbols",
        sa.column("symbol", sa.String),
        sa.column("base_asset", sa.String),
        sa.column("quote_asset", sa.String),
        sa.column("is_active", sa.Boolean),
    )

    conn = op.get_bind()
    for sym in DEFAULT_SYMBOLS:
        exists = conn.execute(
            sa.select(sa.literal(1)).select_from(symbols_table).where(
                symbols_table.c.symbol == sym["symbol"]
            )
        ).scalar()
        if not exists:
            op.execute(
                symbols_table.insert().values(
                    symbol=sym["symbol"],
                    base_asset=sym["base_asset"],
                    quote_asset=sym["quote_asset"],
                    is_active=True,
                )
            )


def downgrade() -> None:
    symbols_table = sa.table(
        "symbols",
        sa.column("symbol", sa.String),
    )
    for sym in DEFAULT_SYMBOLS:
        op.execute(
            symbols_table.delete().where(symbols_table.c.symbol == sym["symbol"])
        )
