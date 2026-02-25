from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.symbol import Symbol
from app.schemas.symbol import SymbolResponse

router = APIRouter()


@router.get("", response_model=list[SymbolResponse])
def list_symbols(db: Session = Depends(get_db)):
    symbols = db.query(Symbol).filter(Symbol.is_active).order_by(Symbol.symbol).all()
    return symbols
