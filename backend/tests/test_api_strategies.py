"""API tests for strategies endpoints (Phase 11.2)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.strategy import Strategy, StrategyVersion
from app.models.user import User

VALID_CONFIG = {
    "rsi_period": 14,
    "rsi_buy_threshold": 30.0,
    "rsi_sell_threshold": 70.0,
    "ma_period": 20,
}


def _create_strategy(
    db: Session, user: User, name: str = "Test Strategy"
) -> Strategy:
    """Helper to create a strategy + v1 directly in DB."""
    s = Strategy(
        user_id=user.id,
        name=name,
        description="Test",
        strategy_type="rsi_ma",
    )
    db.add(s)
    db.flush()
    v = StrategyVersion(
        strategy_id=s.id,
        version_number=1,
        config=VALID_CONFIG,
        is_active=True,
    )
    db.add(v)
    db.flush()
    return s


class TestListStrategies:
    def test_list_own_strategies(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        _create_strategy(db_session, test_user, "Strat A")
        _create_strategy(db_session, test_user, "Strat B")
        resp = client.get("/api/v1/strategies", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {s["name"] for s in data}
        assert "Strat A" in names
        assert "Strat B" in names

    def test_does_not_see_other_users_strategies(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        other_user: User,
        auth_headers: dict,
    ) -> None:
        _create_strategy(db_session, other_user, "Other Strat")
        resp = client.get("/api/v1/strategies", headers=auth_headers)
        assert resp.status_code == 200
        names = [s["name"] for s in resp.json()]
        assert "Other Strat" not in names

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/v1/strategies")
        assert resp.status_code == 401


class TestCreateStrategy:
    def test_create_success(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        resp = client.post(
            "/api/v1/strategies",
            json={
                "name": "My RSI Strategy",
                "description": "A simple RSI strategy",
                "strategy_type": "rsi_ma",
                "config": VALID_CONFIG,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My RSI Strategy"
        assert data["strategy_type"] == "rsi_ma"
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version_number"] == 1
        assert data["versions"][0]["is_active"] is True

    def test_create_invalid_config(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        from pydantic import ValidationError

        with pytest.raises((ValidationError, Exception)):
            client.post(
                "/api/v1/strategies",
                json={
                    "name": "Bad",
                    "strategy_type": "rsi_ma",
                    "config": {"rsi_period": -5},
                },
                headers=auth_headers,
            )

    def test_create_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/strategies",
            json={
                "name": "No Auth",
                "strategy_type": "rsi_ma",
                "config": VALID_CONFIG,
            },
        )
        assert resp.status_code == 401


class TestGetStrategy:
    def test_get_own_strategy(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        s = _create_strategy(db_session, test_user)
        resp = client.get(f"/api/v1/strategies/{s.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == s.id
        assert data["name"] == s.name
        assert "versions" in data

    def test_get_other_users_strategy_404(
        self,
        client: TestClient,
        db_session: Session,
        other_user: User,
        auth_headers: dict,
    ) -> None:
        s = _create_strategy(db_session, other_user)
        resp = client.get(f"/api/v1/strategies/{s.id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_nonexistent_strategy_404(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        resp = client.get("/api/v1/strategies/99999", headers=auth_headers)
        assert resp.status_code == 404


class TestUpdateStrategy:
    def test_update_name(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        s = _create_strategy(db_session, test_user)
        resp = client.patch(
            f"/api/v1/strategies/{s.id}",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_description(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        s = _create_strategy(db_session, test_user)
        resp = client.patch(
            f"/api/v1/strategies/{s.id}",
            json={"description": "New description"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "New description"

    def test_cannot_update_other_users_strategy(
        self,
        client: TestClient,
        db_session: Session,
        other_user: User,
        auth_headers: dict,
    ) -> None:
        s = _create_strategy(db_session, other_user)
        resp = client.patch(
            f"/api/v1/strategies/{s.id}",
            json={"name": "Hacked"},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestCreateVersion:
    def test_create_version(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        s = _create_strategy(db_session, test_user)
        new_config = {**VALID_CONFIG, "rsi_period": 10}
        resp = client.post(
            f"/api/v1/strategies/{s.id}/versions",
            json={"config": new_config},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        versions = resp.json()["versions"]
        assert len(versions) == 2
        active = [v for v in versions if v["is_active"]]
        assert len(active) == 1
        assert active[0]["version_number"] == 2
        assert active[0]["config"]["rsi_period"] == 10

    def test_create_version_invalid_config(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        from pydantic import ValidationError

        s = _create_strategy(db_session, test_user)
        with pytest.raises((ValidationError, Exception)):
            client.post(
                f"/api/v1/strategies/{s.id}/versions",
                json={"config": {"rsi_period": -1}},
                headers=auth_headers,
            )


class TestDeleteStrategy:
    def test_delete_own_strategy(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        s = _create_strategy(db_session, test_user)
        sid = s.id
        resp = client.delete(f"/api/v1/strategies/{sid}", headers=auth_headers)
        assert resp.status_code == 204
        # Confirm it's gone
        resp2 = client.get(f"/api/v1/strategies/{sid}", headers=auth_headers)
        assert resp2.status_code == 404

    def test_delete_other_users_strategy_404(
        self,
        client: TestClient,
        db_session: Session,
        other_user: User,
        auth_headers: dict,
    ) -> None:
        s = _create_strategy(db_session, other_user)
        resp = client.delete(f"/api/v1/strategies/{s.id}", headers=auth_headers)
        assert resp.status_code == 404
