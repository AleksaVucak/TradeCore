"""TOTP service — generate secrets, build provisioning URIs, verify codes (Phase 15.3)."""

from __future__ import annotations

import pyotp

APP_NAME = "TradeCore"


def generate_secret() -> str:
    """Return a new base32 TOTP secret."""
    return pyotp.random_base32()


def build_provisioning_uri(secret: str, email: str) -> str:
    """Return an otpauth:// URI suitable for QR-code scanning."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=APP_NAME)


def verify_code(secret: str, code: str) -> bool:
    """Validate a 6-digit TOTP code (allows ±1 window for clock drift)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
