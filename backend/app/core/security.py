from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


# Bcrypt only uses the first 72 bytes of the password; passlib raises if given more.
_MAX_BCRYPT_BYTES = 72


def _truncate_for_bcrypt(password: str) -> str:
    if not isinstance(password, str):
        password = str(password)
    encoded = password.encode("utf-8")
    if len(encoded) <= _MAX_BCRYPT_BYTES:
        return password
    return encoded[:_MAX_BCRYPT_BYTES].decode("utf-8", errors="replace")


def _hash_with_truncation(password: str) -> str:
    password = _truncate_for_bcrypt(password)
    try:
        return pwd_context.hash(password)
    except Exception as e:
        if "72" in str(e):
            password = password.encode("utf-8")[:72].decode("utf-8", errors="replace")
            return pwd_context.hash(password)
        raise


def _verify_with_truncation(plain_password: str, hashed_password: str) -> bool:
    plain_password = _truncate_for_bcrypt(plain_password)
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        if "72" in str(e):
            plain_password = plain_password.encode("utf-8")[:72].decode("utf-8", errors="replace")
            return pwd_context.verify(plain_password, hashed_password)
        raise


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _verify_with_truncation(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return _hash_with_truncation(password)


def create_access_token(subject: str | int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(subject), "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None
