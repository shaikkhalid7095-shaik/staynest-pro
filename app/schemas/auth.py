from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserOut


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    full_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")
    # only these two can sign up themselves; staff and admin are created by others
    role: Literal["CUSTOMER", "HOTEL_OWNER"] = "CUSTOMER"


class RegisterResponse(BaseModel):
    user: UserOut
    verification_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenOnly(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=64)


class MessageResponse(BaseModel):
    message: str
