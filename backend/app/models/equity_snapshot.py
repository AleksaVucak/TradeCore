from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    backtest_run_id: Mapped[str] = mapped_column(
        ForeignKey("backtest_runs.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    equity_value: Mapped[float] = mapped_column(Float, nullable=False)

    backtest_run: Mapped["BacktestRun"] = relationship(back_populates="equity_snapshots")

