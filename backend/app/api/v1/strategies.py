from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.models.strategy import Strategy
from app.schemas.strategy import StrategyListItem

router = APIRouter()


@router.get("", response_model=list[StrategyListItem])
def list_strategies(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    strategies = (
        db.query(Strategy)
        .filter(Strategy.user_id == user_id)
        .order_by(Strategy.created_at.desc())
        .limit(limit)
        .all()
    )
    return strategies
