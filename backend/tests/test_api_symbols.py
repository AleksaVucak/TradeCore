"""API tests for symbols endpoints (Phase 11.2)."""

from fastapi.testclient import TestClient

from app.models.symbol import Symbol


class TestListSymbols:
    def test_returns_active_only(
        self, client: TestClient, test_symbols: list[Symbol]
    ) -> None:
        resp = client.get("/api/v1/symbols")
        assert resp.status_code == 200
        data = resp.json()
        symbols = [s["symbol"] for s in data]
        assert "BTCUSD" in symbols
        assert "ETHUSD" in symbols
        # XYZUSD was set inactive by the fixture, so it shouldn't appear
        assert "XYZUSD" not in symbols

    def test_response_fields(
        self, client: TestClient, test_symbols: list[Symbol]
    ) -> None:
        resp = client.get("/api/v1/symbols")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        for s in data:
            assert "id" in s
            assert "symbol" in s
            assert "base_asset" in s
            assert "quote_asset" in s
            assert "is_active" in s
            assert s["is_active"] is True

    def test_sorted_by_symbol(
        self, client: TestClient, test_symbols: list[Symbol]
    ) -> None:
        resp = client.get("/api/v1/symbols")
        data = resp.json()
        names = [s["symbol"] for s in data]
        assert names == sorted(names)

    def test_returns_list(self, client: TestClient) -> None:
        resp = client.get("/api/v1/symbols")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_no_auth_required(self, client: TestClient, test_symbols: list) -> None:
        resp = client.get("/api/v1/symbols")
        assert resp.status_code == 200
