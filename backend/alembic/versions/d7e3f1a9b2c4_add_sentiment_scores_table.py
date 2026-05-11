"""add sentiment_scores table

Revision ID: d7e3f1a9b2c4
Revises: c5a8f2d7e9b1
Create Date: 2026-05-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7e3f1a9b2c4"
down_revision: Union[str, Sequence[str], None] = "c5a8f2d7e9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sentiment_scores",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "symbol_id",
            sa.Integer(),
            sa.ForeignKey("symbols.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("sentiment_scores")
