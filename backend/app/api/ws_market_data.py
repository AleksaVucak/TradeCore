"""WebSocket endpoints for market data progress updates."""

from asyncio import sleep
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.fetch_job import FetchJob

router = APIRouter()

POLL_INTERVAL_SECONDS = 1.0


def _serialize_fetch_job(job: FetchJob) -> dict[str, object | None]:
    return {
        "job_id": str(job.id),
        "status": job.status,
        "symbol_id": job.symbol_id,
        "timeframe": job.timeframe,
        "start_date": job.start_date.isoformat().replace("+00:00", "Z"),
        "end_date": job.end_date.isoformat().replace("+00:00", "Z"),
        "total_chunks": job.total_chunks,
        "completed_chunks": job.completed_chunks,
        "candles_fetched": job.candles_fetched,
        "progress_pct": job.progress_pct,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat().replace("+00:00", "Z"),
        "started_at": (
            job.started_at.isoformat().replace("+00:00", "Z") if job.started_at else None
        ),
        "completed_at": (
            job.completed_at.isoformat().replace("+00:00", "Z") if job.completed_at else None
        ),
    }


@router.websocket("/ws/market-data/{job_id}")
async def market_data_progress_websocket(websocket: WebSocket, job_id: UUID) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return

    user_id = decode_access_token(token)
    if user_id is None:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return

    await websocket.accept()

    last_payload: dict[str, object | None] | None = None

    try:
        while True:
            with SessionLocal() as db:
                job = db.get(FetchJob, job_id)
                if not job or job.user_id != int(user_id):
                    await websocket.close(code=4404, reason="Fetch job not found")
                    return

                payload = _serialize_fetch_job(job)
                if payload != last_payload:
                    await websocket.send_json(payload)
                    last_payload = payload

                if job.status in {"completed", "failed"}:
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                    return

            await sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return
