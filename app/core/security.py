import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _create_token(user_id: int, token_type: str, lifetime: timedelta, extra: dict | None = None):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + lifetime,
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, payload


def create_access_token(user_id: int, role: str) -> str:
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    token, _ = _create_token(user_id, "access", lifetime, {"role": role})
    return token


def create_refresh_token(user_id: int):
    # returns the token AND its payload, because we save the jti in the database
    lifetime = timedelta(days=settings.refresh_token_expire_days)
    return _create_token(user_id, "refresh", lifetime)


def create_purpose_token(user_id: int, purpose: str, minutes: int) -> str:
    # used for email verification and password reset links
    token, _ = _create_token(user_id, purpose, timedelta(minutes=minutes))
    return token


def decode_token(token: str) -> dict:
    # raises jwt.PyJWTError if the token is fake, edited or expired
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
