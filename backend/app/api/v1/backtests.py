from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.models.backtest_run import BacktestRun
from app.schemas.backtest import BacktestRunListItem

router = APIRouter()


@router.get("", response_model=list[BacktestRunListItem])
def list_backtests(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = 20,
):
    runs = (
        db.query(BacktestRun)
        .filter(BacktestRun.user_id == user_id)
        .order_by(BacktestRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return runs
