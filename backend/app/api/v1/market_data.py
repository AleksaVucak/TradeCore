"""Market data API: trigger ingestion and query candles."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user_id
from app.models.candle import Candle
from app.schemas.market_data import CandleResponse, IngestRequest, IngestResponse
from app.tasks.market_data import ingest_candles_task

router = APIRouter()

MAX_CANDLES = 5000


@router.post("/ingest", response_model=IngestResponse)
def trigger_ingest(
    body: IngestRequest,
    _user_id: int = Depends(get_current_user_id),
):
    """Enqueue a Celery task to ingest OHLCV for the given symbol and range."""
    task = ingest_candles_task.delay(
        symbol_id=body.symbol_id,
        timeframe=body.timeframe,
        start_date=body.start_date.isoformat(),
        end_date=body.end_date.isoformat(),
    )
    return IngestResponse(message="Ingestion started", task_id=task.id)


@router.get("/candles", response_model=list[CandleResponse])
def list_candles(
    symbol_id: int = Query(..., description="Symbol id"),
    timeframe: str = Query(..., description="1h or 4h"),
    start: datetime = Query(..., description="Start time (UTC)"),
    end: datetime = Query(..., description="End time (UTC)"),
    limit: int = Query(MAX_CANDLES, le=MAX_CANDLES, ge=1),
    db: Session = Depends(get_db),
    _user_id: int = Depends(get_current_user_id),
):
    """Return candles for the given symbol, timeframe, and time range."""
    q = (
        select(Candle)
        .where(
            Candle.symbol_id == symbol_id,
            Candle.timeframe == timeframe,
            Candle.timestamp >= start,
            Candle.timestamp <= end,
        )
        .order_by(Candle.timestamp)
        .limit(limit)
    )
    result = db.execute(q)
    candles = result.scalars().all()
    return list(candles)
