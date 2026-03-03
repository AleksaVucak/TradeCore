import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    backtest_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("backtest_runs.id"), nullable=False, unique=True, index=True
    )
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    backtest_run: Mapped["BacktestRun"] = relationship(back_populates="metrics")

