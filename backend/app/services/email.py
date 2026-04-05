"""Email service for sending verification emails (Phase 15.1).

When MAIL_ENABLED=true, sends via SMTP.
When MAIL_ENABLED=false (default for local dev), logs the verification link to stdout.
"""

from __future__ import annotations

import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User

logger = get_logger(__name__)

TOKEN_BYTES = 32


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash of the raw token (we never store the plaintext)."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_verification_token(db: Session, user: User) -> str:
    """Generate a verification token, persist its hash, and return the raw token."""
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.verification_token_expire_minutes
    )
    record = EmailVerificationToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=expires_at,
    )
    db.add(record)
    db.flush()
    return raw_token


def send_verification_email(user: User, raw_token: str) -> None:
    """Send (or log) the verification email."""
    verify_url = (
        f"{settings.frontend_url}/verify-email?token={raw_token}"
    )

    if not settings.mail_enabled:
        logger.info(
            "verification_email_dev",
            user_id=user.id,
            email=user.email,
            verify_url=verify_url,
        )
        print(
            f"\n{'=' * 60}\n"
            f"  EMAIL VERIFICATION (dev mode)\n"
            f"  To:   {user.email}\n"
            f"  Link: {verify_url}\n"
            f"{'=' * 60}\n"
        )
        return

    subject = f"{settings.mail_from_name} — Verify your email"
    html_body = _build_html(user.email, verify_url)
    plain_body = (
        f"Hi {user.email},\n\n"
        f"Click the link below to verify your email:\n{verify_url}\n\n"
        f"This link expires in {settings.verification_token_expire_minutes} minutes.\n\n"
        f"— {settings.mail_from_name}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.mail_from_name} <{settings.mail_from_address}>"
    msg["To"] = user.email
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.mail_smtp_host, settings.mail_smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.mail_smtp_user, settings.mail_smtp_password)
            server.sendmail(settings.mail_from_address, [user.email], msg.as_string())
        logger.info("verification_email_sent", user_id=user.id, email=user.email)
    except Exception:
        logger.exception("verification_email_failed", user_id=user.id, email=user.email)


def verify_token(db: Session, raw_token: str) -> User | None:
    """Validate a raw token: mark it used, set email_verified, return the user.

    Returns None if the token is invalid, expired, or already used.
    """
    token_hash = _hash_token(raw_token)
    record = (
        db.query(EmailVerificationToken)
        .filter(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.used.is_(False),
        )
        .first()
    )
    if record is None:
        return None

    if record.expires_at.tzinfo is None:
        expires_at = record.expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = record.expires_at

    if expires_at < datetime.now(timezone.utc):
        return None

    record.used = True
    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        return None

    user.email_verified = True
    db.flush()
    return user


def last_token_created_at(db: Session, user_id: int) -> datetime | None:
    """Return the created_at of the newest verification token for this user."""
    record = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.user_id == user_id)
        .order_by(EmailVerificationToken.created_at.desc())
        .first()
    )
    return record.created_at if record else None


def _build_html(email: str, verify_url: str) -> str:
    return f"""\
<html>
<body style="font-family:sans-serif;padding:24px;">
  <h2>Verify your email</h2>
  <p>Hi {email},</p>
  <p>Click the button below to verify your email address:</p>
  <a href="{verify_url}"
     style="display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;
            border-radius:6px;text-decoration:none;font-weight:600;">
    Verify email
  </a>
  <p style="margin-top:16px;color:#666;font-size:14px;">
    Or copy this link: {verify_url}
  </p>
  <p style="color:#999;font-size:12px;">
    This link expires in {settings.verification_token_expire_minutes} minutes.
  </p>
</body>
</html>"""
