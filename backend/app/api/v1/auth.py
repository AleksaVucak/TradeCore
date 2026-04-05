"""Auth routes — register, login, verify, resend, 2FA setup/confirm/disable (Phases 15.1–15.3)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.core.security import create_access_token, get_password_hash, verify_password
from app.dependencies import get_current_user_id, get_db
from app.models.user import User
from app.schemas.user import (
    RegisterResponse,
    ResendVerificationResponse,
    Token,
    TwoFactorDisableRequest,
    TwoFactorDisableResponse,
    TwoFactorSetupConfirmRequest,
    TwoFactorSetupConfirmResponse,
    TwoFactorSetupStartResponse,
    UserCreate,
    UserResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.services.email import (
    create_verification_token,
    last_token_created_at,
    send_verification_email,
    verify_token,
)
from app.services.totp import build_provisioning_uri, generate_secret, verify_code

logger = get_logger(__name__)

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        logger.warning("registration_failed", reason="email_exists", email=user_in.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    try:
        user = User(
            email=user_in.email,
            hashed_password=get_password_hash(user_in.password),
        )
        db.add(user)
        db.flush()

        raw_token = create_verification_token(db, user)
        db.commit()
        db.refresh(user)

        send_verification_email(user, raw_token)

        logger.info("user_registered", user_id=user.id, email=user.email)
        return RegisterResponse(
            id=user.id,
            email=user.email,
            email_verified=user.email_verified,
            message="Verification email sent. Please check your inbox.",
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("registration_error", email=user_in.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning("login_failed", email=form.username, reason="invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.email_verified:
        logger.warning("login_failed", email=form.username, reason="email_not_verified")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox and verify your email before logging in.",
        )

    token = create_access_token(subject=user.id)
    logger.info("login_success", user_id=user.id, email=user.email)
    return Token(access_token=token)


@router.post("/verify-email", response_model=VerifyEmailResponse)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = verify_token(db, body.token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )
    db.commit()
    logger.info("email_verified", user_id=user.id, email=user.email)
    return VerifyEmailResponse(
        message="Email verified successfully.",
        email_verified=True,
    )


@router.post("/resend-verification", response_model=ResendVerificationResponse)
def resend_verification(user_in: UserCreate, db: Session = Depends(get_db)):
    """Resend a verification email.

    Requires email + password so only the account owner can trigger resends.
    Enforces a cooldown to prevent spam.
    """
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if user.email_verified:
        return ResendVerificationResponse(message="Email is already verified.")

    last_sent = last_token_created_at(db, user.id)
    if last_sent is not None:
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_sent).total_seconds()
        if elapsed < settings.verification_resend_cooldown_seconds:
            wait = int(settings.verification_resend_cooldown_seconds - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait} seconds before requesting another verification email.",
            )

    raw_token = create_verification_token(db, user)
    db.commit()
    send_verification_email(user, raw_token)
    logger.info("verification_resent", user_id=user.id, email=user.email)
    return ResendVerificationResponse(message="Verification email sent.")


@router.get("/me", response_model=UserResponse)
def me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ── 2FA endpoints (Phase 15.3) ──────────────────────────────────────


@router.post("/2fa/setup/start", response_model=TwoFactorSetupStartResponse)
def two_factor_setup_start(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Generate a TOTP secret and return it with a provisioning URI for QR scanning.

    The secret is persisted immediately but totp_enabled stays False until the
    user confirms with a valid code via /2fa/setup/confirm.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled.",
        )

    secret = generate_secret()
    user.totp_secret = secret
    db.commit()

    uri = build_provisioning_uri(secret, user.email)
    logger.info("2fa_setup_started", user_id=user.id)
    return TwoFactorSetupStartResponse(secret=secret, otpauth_uri=uri)


@router.post("/2fa/setup/confirm", response_model=TwoFactorSetupConfirmResponse)
def two_factor_setup_confirm(
    body: TwoFactorSetupConfirmRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Verify the TOTP code the user entered and enable 2FA on their account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled.",
        )

    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start 2FA setup first before confirming.",
        )

    if not verify_code(user.totp_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code. Please try again.",
        )

    user.totp_enabled = True
    db.commit()
    logger.info("2fa_enabled", user_id=user.id)
    return TwoFactorSetupConfirmResponse(
        message="Two-factor authentication enabled successfully.",
        totp_enabled=True,
    )


@router.post("/2fa/disable", response_model=TwoFactorDisableResponse)
def two_factor_disable(
    body: TwoFactorDisableRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Disable 2FA. Requires current password + a valid TOTP code for safety."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled.",
        )

    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    if not user.totp_secret or not verify_code(user.totp_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code. Please try again.",
        )

    user.totp_secret = None
    user.totp_enabled = False
    db.commit()
    logger.info("2fa_disabled", user_id=user.id)
    return TwoFactorDisableResponse(
        message="Two-factor authentication has been disabled.",
        totp_enabled=False,
    )
