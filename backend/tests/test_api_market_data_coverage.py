"""API tests for market data coverage endpoint (Phase 13.2)."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.candle import Candle
from app.models.symbol import Symbol


def _add_candle(
    db_session: Session,
    *,
    symbol_id: int,
    timeframe: str,
    timestamp: datetime,
    price: float,
) -> Candle:
    candle = Candle(
        symbol_id=symbol_id,
        timeframe=timeframe,
        timestamp=timestamp,
        open=price,
        high=price + 1,
        low=price - 1,
        close=price,
        volume=100.0,
    )
    db_session.add(candle)
    db_session.flush()
    return candle


def _add_symbol(
    db_session: Session,
    *,
    symbol: str,
    base_asset: str = "TST",
    quote_asset: str = "USD",
) -> Symbol:
    row = Symbol(symbol=symbol, base_asset=base_asset, quote_asset=quote_asset, is_active=True)
    db_session.add(row)
    db_session.flush()
    return row


class TestGetMarketDataCoverage:
    def test_returns_empty_list_when_filtered_symbol_has_no_candles(
        self,
        client: TestClient,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        inactive_symbol = test_symbols[2]
        resp = client.get(
            f"/api/v1/market-data/coverage?symbol_id={inactive_symbol.id}",
            headers=auth_headers,
        )

        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_grouped_coverage_by_symbol_and_timeframe(
        self,
        client: TestClient,
        db_session: Session,
        auth_headers: dict,
    ) -> None:
        btc = _add_symbol(db_session, symbol="COVBTC2030")
        eth = _add_symbol(db_session, symbol="COVETH2030", base_asset="COV")
        _add_candle(
            db_session,
            symbol_id=btc.id,
            timeframe="1h",
            timestamp=datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc),
            price=100.0,
        )
        _add_candle(
            db_session,
            symbol_id=btc.id,
            timeframe="1h",
            timestamp=datetime(2030, 1, 1, 2, 0, tzinfo=timezone.utc),
            price=102.0,
        )
        _add_candle(
            db_session,
            symbol_id=btc.id,
            timeframe="4h",
            timestamp=datetime(2030, 1, 2, 0, 0, tzinfo=timezone.utc),
            price=200.0,
        )
        _add_candle(
            db_session,
            symbol_id=eth.id,
            timeframe="1h",
            timestamp=datetime(2030, 1, 3, 0, 0, tzinfo=timezone.utc),
            price=300.0,
        )

        resp = client.get("/api/v1/market-data/coverage", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        matching = [row for row in data if row["symbol_id"] in {btc.id, eth.id}]
        assert matching == [
            {
                "symbol_id": btc.id,
                "timeframe": "1h",
                "start_date": "2030-01-01T00:00:00Z",
                "end_date": "2030-01-01T02:00:00Z",
                "candle_count": 2,
            },
            {
                "symbol_id": btc.id,
                "timeframe": "4h",
                "start_date": "2030-01-02T00:00:00Z",
                "end_date": "2030-01-02T00:00:00Z",
                "candle_count": 1,
            },
            {
                "symbol_id": eth.id,
                "timeframe": "1h",
                "start_date": "2030-01-03T00:00:00Z",
                "end_date": "2030-01-03T00:00:00Z",
                "candle_count": 1,
            },
        ]

    def test_filters_by_symbol_id(
        self,
        client: TestClient,
        db_session: Session,
        auth_headers: dict,
    ) -> None:
        btc = _add_symbol(db_session, symbol="COVBTC2031")
        eth = _add_symbol(db_session, symbol="COVETH2031", base_asset="COV")
        _add_candle(
            db_session,
            symbol_id=btc.id,
            timeframe="1h",
            timestamp=datetime(2031, 1, 1, tzinfo=timezone.utc),
            price=100.0,
        )
        _add_candle(
            db_session,
            symbol_id=eth.id,
            timeframe="1h",
            timestamp=datetime(2031, 1, 2, tzinfo=timezone.utc),
            price=200.0,
        )

        resp = client.get(
            f"/api/v1/market-data/coverage?symbol_id={btc.id}",
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["symbol_id"] == btc.id
        assert data[0]["start_date"] == "2031-01-01T00:00:00Z"

    def test_filters_by_timeframe(
        self,
        client: TestClient,
        db_session: Session,
        test_symbols: list[Symbol],
        auth_headers: dict,
    ) -> None:
        btc, _, _ = test_symbols
        _add_candle(
            db_session,
            symbol_id=btc.id,
            timeframe="1h",
            timestamp=datetime(2032, 1, 1, tzinfo=timezone.utc),
            price=100.0,
        )
        _add_candle(
            db_session,
            symbol_id=btc.id,
            timeframe="4h",
            timestamp=datetime(2032, 1, 2, tzinfo=timezone.utc),
            price=200.0,
        )

        resp = client.get(
            "/api/v1/market-data/coverage?timeframe=4h",
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        matching = [row for row in data if row["start_date"].startswith("2032-01")]
        assert len(matching) == 1
        assert matching[0]["timeframe"] == "4h"

    def test_requires_auth(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/api/v1/market-data/coverage")

        assert resp.status_code == 401
