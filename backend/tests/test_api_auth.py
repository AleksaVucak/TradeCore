"""API tests for auth endpoints (Phase 11.2)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User


class TestRegister:
    def test_register_success(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": "securepass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert "id" in data

    def test_register_duplicate_email(
        self, client: TestClient, test_user: User
    ) -> None:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": test_user.email, "password": "anything123"},
        )
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_invalid_email(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "pass123"},
        )
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client: TestClient, test_user: User) -> None:
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": test_user.email, "password": "testpassword123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(
        self, client: TestClient, test_user: User
    ) -> None:
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": test_user.email, "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_unknown_email(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "pass"},
        )
        assert resp.status_code == 401


class TestMe:
    def test_me_authenticated(
        self, client: TestClient, test_user: User, auth_headers: dict
    ) -> None:
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email

    def test_me_no_token(self, client: TestClient) -> None:
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401
