"""Market data API: trigger ingestion and query candles."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user_id
from app.models.candle import Candle
from app.models.fetch_job import FetchJob, FetchJobStatus
from app.models.symbol import Symbol
from app.schemas.market_data import (
    CandleResponse,
    CoverageRangeResponse,
    FetchJobResponse,
    FetchJobStatusResponse,
    FetchRequest,
    IngestRequest,
    IngestResponse,
)
from app.tasks.market_data import fetch_candles_task, ingest_candles_task

router = APIRouter()

MAX_CANDLES = 50_000


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


@router.post("/fetch", response_model=FetchJobResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_fetch(
    body: FetchRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Enqueue a Celery task to fetch OHLCV for the given symbol and date range.
    Returns a FetchJob with job_id that can be polled for status.
    """
    symbol = db.get(Symbol, body.symbol_id)
    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol id {body.symbol_id} not found",
        )

    job = FetchJob(
        user_id=user_id,
        symbol_id=body.symbol_id,
        timeframe=body.timeframe,
        start_date=body.start_date,
        end_date=body.end_date,
        status=FetchJobStatus.PENDING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    task = fetch_candles_task.delay(
        job_id=str(job.id),
        symbol_id=body.symbol_id,
        timeframe=body.timeframe,
        start_date=body.start_date.isoformat(),
        end_date=body.end_date.isoformat(),
    )

    job.celery_task_id = task.id
    db.commit()

    return FetchJobResponse(
        job_id=job.id,
        status=job.status,
        symbol_id=job.symbol_id,
        timeframe=job.timeframe,
        start_date=job.start_date,
        end_date=job.end_date,
        created_at=job.created_at,
        message="Fetch job started",
    )


@router.get("/fetch/{job_id}", response_model=FetchJobStatusResponse)
def get_fetch_status(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Get the status and progress of a fetch job.
    """
    job = db.get(FetchJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fetch job not found",
        )

    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fetch job not found",
        )

    return FetchJobStatusResponse(
        job_id=job.id,
        status=job.status,
        symbol_id=job.symbol_id,
        timeframe=job.timeframe,
        start_date=job.start_date,
        end_date=job.end_date,
        total_chunks=job.total_chunks,
        completed_chunks=job.completed_chunks,
        candles_fetched=job.candles_fetched,
        progress_pct=job.progress_pct,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get("/fetch", response_model=list[FetchJobStatusResponse])
def list_fetch_jobs(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    List fetch jobs for the current user, optionally filtered by status.
    """
    q = select(FetchJob).where(FetchJob.user_id == user_id)
    if status_filter:
        q = q.where(FetchJob.status == status_filter)
    q = q.order_by(FetchJob.created_at.desc()).limit(limit)

    result = db.execute(q)
    jobs = result.scalars().all()

    return [
        FetchJobStatusResponse(
            job_id=job.id,
            status=job.status,
            symbol_id=job.symbol_id,
            timeframe=job.timeframe,
            start_date=job.start_date,
            end_date=job.end_date,
            total_chunks=job.total_chunks,
            completed_chunks=job.completed_chunks,
            candles_fetched=job.candles_fetched,
            progress_pct=job.progress_pct,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
        for job in jobs
    ]


@router.get("/coverage", response_model=list[CoverageRangeResponse])
def get_market_data_coverage(
    db: Session = Depends(get_db),
    _user_id: int = Depends(get_current_user_id),
    symbol_id: int | None = Query(None, description="Optional symbol id filter"),
    timeframe: str | None = Query(None, description="Optional timeframe filter"),
):
    """Return available candle coverage windows grouped by symbol and timeframe."""
    q = (
        select(
            Candle.symbol_id,
            Candle.timeframe,
            func.min(Candle.timestamp).label("start_date"),
            func.max(Candle.timestamp).label("end_date"),
            func.count(Candle.id).label("candle_count"),
        )
        .group_by(Candle.symbol_id, Candle.timeframe)
        .order_by(Candle.symbol_id, Candle.timeframe)
    )
    if symbol_id is not None:
        q = q.where(Candle.symbol_id == symbol_id)
    if timeframe is not None:
        q = q.where(Candle.timeframe == timeframe)

    rows = db.execute(q).all()
    return [
        CoverageRangeResponse(
            symbol_id=row.symbol_id,
            timeframe=row.timeframe,
            start_date=row.start_date,
            end_date=row.end_date,
            candle_count=row.candle_count,
        )
        for row in rows
    ]


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
