"""API tests for auth endpoints (Phase 11.2 + Phase 15.1 email verification)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User
from app.services.email import _hash_token


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
class TestRegister:
    def test_register_success(self, client: TestClient) -> None:
        with patch("app.api.v1.auth.send_verification_email") as mock_send:
            resp = client.post(
                "/api/v1/auth/register",
                json={"email": "new@example.com", "password": "securepass123"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert data["email_verified"] is False
        assert "id" in data
        assert "message" in data
        mock_send.assert_called_once()

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

    def test_register_creates_verification_token(
        self, client: TestClient, db_session: Session
    ) -> None:
        with patch("app.api.v1.auth.send_verification_email"):
            resp = client.post(
                "/api/v1/auth/register",
                json={"email": "tokencheck@example.com", "password": "securepass123"},
            )
        assert resp.status_code == 201
        user_id = resp.json()["id"]
        token = (
            db_session.query(EmailVerificationToken)
            .filter(EmailVerificationToken.user_id == user_id)
            .first()
        )
        assert token is not None
        assert token.used is False


# ---------------------------------------------------------------------------
# Login — hard gate
# ---------------------------------------------------------------------------
class TestLogin:
    def test_login_success_verified(self, client: TestClient, test_user: User) -> None:
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": test_user.email, "password": "testpassword123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_blocked_unverified(
        self, client: TestClient, db_session: Session
    ) -> None:
        """An unverified user must be rejected with 403."""
        from app.core.security import get_password_hash

        user = User(
            email="unverified@example.com",
            hashed_password=get_password_hash("pass123"),
            email_verified=False,
        )
        db_session.add(user)
        db_session.flush()

        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "unverified@example.com", "password": "pass123"},
        )
        assert resp.status_code == 403
        assert "not verified" in resp.json()["detail"].lower()

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


# ---------------------------------------------------------------------------
# Verify email
# ---------------------------------------------------------------------------
class TestVerifyEmail:
    def _create_unverified_user_with_token(
        self, db_session: Session, raw_token: str = "test-raw-token-abc123",
        expired: bool = False, used: bool = False,
    ) -> tuple[User, str]:
        from app.core.security import get_password_hash

        user = User(
            email="verify-me@example.com",
            hashed_password=get_password_hash("pass123"),
            email_verified=False,
        )
        db_session.add(user)
        db_session.flush()

        if expired:
            expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        token = EmailVerificationToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=expires_at,
            used=used,
        )
        db_session.add(token)
        db_session.flush()
        return user, raw_token

    def test_verify_success(
        self, client: TestClient, db_session: Session
    ) -> None:
        user, raw_token = self._create_unverified_user_with_token(db_session)
        resp = client.post(
            "/api/v1/auth/verify-email",
            json={"token": raw_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email_verified"] is True
        assert "verified" in data["message"].lower()

        db_session.refresh(user)
        assert user.email_verified is True

    def test_verify_expired_token(
        self, client: TestClient, db_session: Session
    ) -> None:
        _, raw_token = self._create_unverified_user_with_token(
            db_session, raw_token="expired-token-xyz", expired=True
        )
        resp = client.post(
            "/api/v1/auth/verify-email",
            json={"token": raw_token},
        )
        assert resp.status_code == 400

    def test_verify_already_used_token(
        self, client: TestClient, db_session: Session
    ) -> None:
        _, raw_token = self._create_unverified_user_with_token(
            db_session, raw_token="used-token-xyz", used=True
        )
        resp = client.post(
            "/api/v1/auth/verify-email",
            json={"token": raw_token},
        )
        assert resp.status_code == 400

    def test_verify_invalid_token(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/verify-email",
            json={"token": "totally-bogus-token"},
        )
        assert resp.status_code == 400

    def test_verify_then_login(
        self, client: TestClient, db_session: Session
    ) -> None:
        user, raw_token = self._create_unverified_user_with_token(
            db_session, raw_token="verify-then-login-token"
        )
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": user.email, "password": "pass123"},
        )
        assert resp.status_code == 403

        client.post("/api/v1/auth/verify-email", json={"token": raw_token})

        resp = client.post(
            "/api/v1/auth/login",
            data={"username": user.email, "password": "pass123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------
class TestResendVerification:
    def test_resend_success(
        self, client: TestClient, db_session: Session
    ) -> None:
        from app.core.security import get_password_hash

        user = User(
            email="resend@example.com",
            hashed_password=get_password_hash("pass123"),
            email_verified=False,
        )
        db_session.add(user)
        db_session.flush()

        with patch("app.api.v1.auth.send_verification_email") as mock_send:
            resp = client.post(
                "/api/v1/auth/resend-verification",
                json={"email": "resend@example.com", "password": "pass123"},
            )
        assert resp.status_code == 200
        assert "sent" in resp.json()["message"].lower()
        mock_send.assert_called_once()

    def test_resend_already_verified(
        self, client: TestClient, test_user: User
    ) -> None:
        resp = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": test_user.email, "password": "testpassword123"},
        )
        assert resp.status_code == 200
        assert "already verified" in resp.json()["message"].lower()

    def test_resend_wrong_password(self, client: TestClient, db_session: Session) -> None:
        from app.core.security import get_password_hash

        user = User(
            email="resend-wrong@example.com",
            hashed_password=get_password_hash("pass123"),
            email_verified=False,
        )
        db_session.add(user)
        db_session.flush()

        resp = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "resend-wrong@example.com", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_resend_cooldown(
        self, client: TestClient, db_session: Session
    ) -> None:
        from app.core.security import get_password_hash

        user = User(
            email="cooldown@example.com",
            hashed_password=get_password_hash("pass123"),
            email_verified=False,
        )
        db_session.add(user)
        db_session.flush()

        token = EmailVerificationToken(
            user_id=user.id,
            token_hash=_hash_token("cooldown-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(token)
        db_session.flush()

        with patch("app.api.v1.auth.send_verification_email"):
            resp = client.post(
                "/api/v1/auth/resend-verification",
                json={"email": "cooldown@example.com", "password": "pass123"},
            )
        assert resp.status_code == 429
        assert "wait" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /me — includes new fields
# ---------------------------------------------------------------------------
class TestMe:
    def test_me_authenticated(
        self, client: TestClient, test_user: User, auth_headers: dict
    ) -> None:
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["email_verified"] is True
        assert data["totp_enabled"] is False

    def test_me_no_token(self, client: TestClient) -> None:
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401
