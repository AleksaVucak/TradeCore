"""add sentiment dedup indexes (Phase 17.6)

Revision ID: e8f2a6b3c1d5
Revises: d7e3f1a9b2c4
Create Date: 2026-05-12

Adds a composite unique index on (symbol_id, headline, published_at) and a
partial unique index on (symbol_id, url) WHERE url IS NOT NULL to enforce
dedup at the database level as a safety net alongside the application-level
checks in the pipeline.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e8f2a6b3c1d5"
down_revision: Union[str, Sequence[str], None] = "d7e3f1a9b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_sentiment_scores_dedup",
        "sentiment_scores",
        ["symbol_id", "headline", "published_at"],
        unique=True,
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_sentiment_scores_url_dedup "
        "ON sentiment_scores (symbol_id, url) WHERE url IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sentiment_scores_url_dedup")
    op.drop_index("ix_sentiment_scores_dedup", table_name="sentiment_scores")
