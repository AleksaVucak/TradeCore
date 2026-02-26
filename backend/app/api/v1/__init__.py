from fastapi import APIRouter

from app.api.v1 import auth, backtests, market_data, strategies, symbols

api_router = APIRouter(prefix="/api/v1", tags=["api"])

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(symbols.router, prefix="/symbols", tags=["symbols"])
api_router.include_router(backtests.router, prefix="/backtests", tags=["backtests"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(market_data.router, prefix="/market-data", tags=["market-data"])
