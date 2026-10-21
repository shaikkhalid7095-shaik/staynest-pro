import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.database import SessionLocal
from app.models import User

# tells Swagger where to send username/password for the "Authorize" button
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    not_valid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise not_valid

    # a refresh token must not work as an access token
    if payload.get("type") != "access":
        raise not_valid

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise not_valid
    return user


def require_roles(*allowed_roles):
    # usage: user = Depends(require_roles(RoleName.ADMIN, RoleName.HOTEL_OWNER))
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission for this action",
            )
        return user

    return checker
