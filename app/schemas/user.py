from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    phone: str | None
    role: str
    is_active: bool
    is_email_verified: bool
    created_at: datetime

    @classmethod
    def from_user(cls, user):
        # user.role is a Role object, but we want just the name in the response
        data = {c: getattr(user, c) for c in cls.model_fields if c != "role"}
        return cls(**data, role=user.role.name)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")


class CustomerProfileUpdate(BaseModel):
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=20)
    address_line: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    profile_image_url: str | None = Field(default=None, max_length=500)


class CustomerProfileOut(CustomerProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    updated_at: datetime
