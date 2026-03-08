"""
Shared test fixtures for API tests (Phase 11.2).

Uses the same Postgres database but wraps each test in a rolled-back transaction
so tests don't persist data or interfere with each other.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.base import Base
from app.dependencies import get_db
from app.main import app
from app.models.user import User
from app.models.symbol import Symbol

TEST_DB_URL = settings.database_url

engine = create_engine(TEST_DB_URL, future=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    """
    Provide a transactional DB session that rolls back after each test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def end_savepoint(session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session: Session):
    """
    FastAPI TestClient with DB dependency overridden to use the transactional session.
    """
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def test_user(db_session: Session) -> User:
    """Create and return a test user."""
    user = User(
        email="testuser@example.com",
        hashed_password=get_password_hash("testpassword123"),
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def test_user_token(test_user: User) -> str:
    """Return a valid JWT bearer token for the test user."""
    return create_access_token(subject=test_user.id)


@pytest.fixture()
def auth_headers(test_user_token: str) -> dict[str, str]:
    """Return authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture()
def other_user(db_session: Session) -> User:
    """Create a second test user for permission tests."""
    user = User(
        email="other@example.com",
        hashed_password=get_password_hash("otherpassword123"),
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def other_auth_headers(other_user: User) -> dict[str, str]:
    """Return authorization headers for the other user."""
    token = create_access_token(subject=other_user.id)
    return {"Authorization": f"Bearer {token}"}


def _get_or_create_symbol(
    db: Session, symbol: str, base: str, quote: str, active: bool
) -> Symbol:
    """Return an existing symbol or create a new one."""
    existing = db.query(Symbol).filter(Symbol.symbol == symbol).first()
    if existing:
        existing.is_active = active
        db.flush()
        return existing
    s = Symbol(symbol=symbol, base_asset=base, quote_asset=quote, is_active=active)
    db.add(s)
    db.flush()
    return s


@pytest.fixture()
def test_symbols(db_session: Session) -> list[Symbol]:
    """Return two active symbols and one inactive symbol."""
    btc = _get_or_create_symbol(db_session, "BTCUSD", "BTC", "USD", True)
    eth = _get_or_create_symbol(db_session, "ETHUSD", "ETH", "USD", True)
    inactive = _get_or_create_symbol(db_session, "XYZUSD", "XYZ", "USD", False)
    return [btc, eth, inactive]
