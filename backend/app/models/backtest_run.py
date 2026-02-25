from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BacktestRunStatus:
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    strategy_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False, index=True
    )
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=BacktestRunStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(String(1000))
    run_options: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="backtest_runs")
    strategy_version: Mapped["StrategyVersion"] = relationship(back_populates="backtest_runs")
    symbol: Mapped["Symbol"] = relationship(back_populates="backtest_runs")
    trades: Mapped[list["Trade"]] = relationship(
        back_populates="backtest_run", cascade="all, delete-orphan"
    )
    equity_snapshots: Mapped[list["EquitySnapshot"]] = relationship(
        back_populates="backtest_run", cascade="all, delete-orphan"
    )
    metrics: Mapped["MetricSnapshot"] = relationship(
        back_populates="backtest_run", uselist=False, cascade="all, delete-orphan"
    )

