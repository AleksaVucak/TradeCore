from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import redis

from app.api.v1 import api_router
from app.config import settings
from app.db.session import SessionLocal

app = FastAPI(
    title="TradeCore API",
    description="Strategy research and paper-trading platform for crypto spot markets",
    version="0.1.0",
)

# Allow localhost / 127.0.0.1 on any port for local dev (avoids CORS "Failed to fetch")
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe that checks database and Redis connectivity."""
    # Database check
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "detail": "database not reachable"},
        )

    # Redis check
    try:
        client = redis.Redis.from_url(settings.redis_url)
        client.ping()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "detail": "redis not reachable"},
        )

    return {"status": "ready"}
