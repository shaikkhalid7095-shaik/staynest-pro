from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas.auth import (
    ForgotPasswordRequest, MessageResponse, RefreshRequest, RegisterRequest,
    RegisterResponse, ResetPasswordRequest, TokenOnly, TokenResponse,
)
from app.schemas.user import UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    user, token = auth_service.register_user(db, data)
    return RegisterResponse(user=UserOut.from_user(user), verification_token=token)


@router.post("/login", response_model=TokenResponse)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form calls the field "username" - we put the email in it
    from app.services.audit_service import client_ip  # day 4: remember where logins come from

    return auth_service.login(db, form.username, form.password, client_ip(request))


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    return auth_service.refresh(db, data.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(data: RefreshRequest, db: Session = Depends(get_db)):
    auth_service.logout(db, data.refresh_token)
    return {"message": "Logged out"}


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    auth_service.revoke_all_tokens(db, user.id)
    db.commit()
    return {"message": "Logged out from all devices"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.from_user(user)


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(data: TokenOnly, db: Session = Depends(get_db)):
    auth_service.verify_email(db, data.token)
    return {"message": "Email verified"}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    token = auth_service.forgot_password(db, data.email)
    # same message either way, so nobody can check which emails are registered
    # reset_token is returned only because we have no email service yet
    return {"message": "If this email exists, a reset link has been sent", "reset_token": token}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, data.token, data.new_password)
    return {"message": "Password changed. Please log in again"}
