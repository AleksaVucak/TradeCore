from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    backtest_run_id: Mapped[str] = mapped_column(
        ForeignKey("backtest_runs.id"), nullable=False, unique=True, index=True
    )
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    backtest_run: Mapped["BacktestRun"] = relationship(back_populates="metrics")

