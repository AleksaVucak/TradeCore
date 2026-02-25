from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegimeLabel(Base):
    __tablename__ = "regime_labels"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("ml_model_metadata.id"), index=True)
    backtest_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("backtest_runs.id"), index=True
    )
    symbol_id: Mapped[int | None] = mapped_column(ForeignKey("symbols.id"), index=True)
    timeframe: Mapped[str | None] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    regime: Mapped[str] = mapped_column(String(32), nullable=False)

