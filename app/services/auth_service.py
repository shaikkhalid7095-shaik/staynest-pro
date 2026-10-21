from datetime import datetime, timezone

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token, create_purpose_token, create_refresh_token,
    decode_token, hash_password, verify_password,
)
from app.models import CustomerProfile, LoginAttempt, RefreshToken, Role, RoleName, User
from app.schemas.auth import RegisterRequest, TokenResponse

VERIFY_EMAIL_MINUTES = 60 * 24
RESET_PASSWORD_MINUTES = 30


def utcnow():
    # MySQL DATETIME has no timezone, so we store plain UTC times
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _read_token(token: str, expected_type: str) -> dict:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    return payload


def register_user(db: Session, data: RegisterRequest):
    email = data.email.lower()

    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    if data.phone and db.scalar(select(User).where(User.phone == data.phone)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone number is already registered")

    role = db.scalar(select(Role).where(Role.name == data.role))
    if role is None:
        # happens if you forgot to run: python -m app.db.seed
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Roles are not set up yet")

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role=role,
    )
    if role.name == RoleName.CUSTOMER:
        # every customer gets an empty profile they can fill later
        user.customer_profile = CustomerProfile()

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_purpose_token(user.id, "verify_email", VERIFY_EMAIL_MINUTES)
    return user, token


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    access = create_access_token(user.id, user.role.name)
    refresh, payload = create_refresh_token(user.id)

    db.add(RefreshToken(
        user_id=user.id,
        jti=payload["jti"],
        expires_at=payload["exp"].replace(tzinfo=None),
    ))
    db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


def login(db: Session, email: str, password: str, ip: str | None = None) -> TokenResponse:
    from app.services import audit_service, settings_service  # day 4: lockout + audit

    email = email.lower().strip()
    max_failed = settings_service.get_int(db, "max_failed_logins")
    lockout = settings_service.get_int(db, "lockout_minutes")

    # too many wrong passwords recently: stop here, even if this one is right
    if audit_service.recent_failures(db, email, lockout) >= max_failed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {lockout} minutes",
        )

    user = db.scalar(select(User).where(User.email == email))

    # same message for wrong email and wrong password, so attackers can't guess emails
    if user is None or not verify_password(password, user.password_hash):
        db.add(LoginAttempt(email=email, success=False, ip_address=ip))
        audit_service.log(db, user.id if user else None, "LOGIN_FAILED", "user", user.id if user else None, email, ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is blocked")

    db.add(LoginAttempt(email=email, success=True, ip_address=ip))
    audit_service.log(db, user.id, "LOGIN", "user", user.id, None, ip)
    user.last_login_at = utcnow()
    return _issue_tokens(db, user)


def refresh(db: Session, refresh_token: str) -> TokenResponse:
    payload = _read_token(refresh_token, "refresh")
    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))

    if row is None or row.revoked or row.expires_at < utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is no longer valid")
    if not row.user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is blocked")

    # rotation: the old refresh token can't be used again
    row.revoked = True
    return _issue_tokens(db, row.user)


def logout(db: Session, refresh_token: str):
    payload = _read_token(refresh_token, "refresh")
    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if row and not row.revoked:
        row.revoked = True
        db.commit()


def revoke_all_tokens(db: Session, user_id: int):
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )


def verify_email(db: Session, token: str):
    payload = _read_token(token, "verify_email")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.is_email_verified = True
    db.commit()


def forgot_password(db: Session, email: str) -> str | None:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        return None
    return create_purpose_token(user.id, "reset_password", RESET_PASSWORD_MINUTES)


def reset_password(db: Session, token: str, new_password: str):
    payload = _read_token(token, "reset_password")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.password_hash = hash_password(new_password)
    # log the user out everywhere after a password change
    revoke_all_tokens(db, user.id)
    db.commit()
