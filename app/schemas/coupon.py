from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=255)
    discount_type: Literal["PERCENT", "FLAT"]
    discount_value: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    max_discount: Decimal | None = Field(default=None, gt=0)
    min_booking_amount: Decimal = Field(default=Decimal("0"), ge=0)
    valid_from: datetime
    valid_until: datetime
    usage_limit: int | None = Field(default=None, ge=1)
    per_user_limit: int = Field(default=1, ge=1)
    hotel_id: int | None = None  # required for hotel owners, optional for admin

    @field_validator("code")
    @classmethod
    def upper_code(cls, value: str) -> str:
        # store codes in capitals so "save10" and "SAVE10" are the same coupon
        return value.upper()

    @model_validator(mode="after")
    def check_values(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if self.discount_type == "PERCENT" and self.discount_value > 100:
            raise ValueError("A percent discount can't be more than 100")
        return self


class CouponUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    max_discount: Decimal | None = Field(default=None, gt=0)
    valid_until: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class CouponOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: str | None
    discount_type: str
    discount_value: Decimal
    max_discount: Decimal | None
    min_booking_amount: Decimal
    valid_from: datetime
    valid_until: datetime
    usage_limit: int | None
    used_count: int
    per_user_limit: int
    hotel_id: int | None
    is_active: bool


class CouponValidateRequest(BaseModel):
    code: str
    hotel_id: int
    amount: Decimal = Field(gt=0)


class CouponValidateResponse(BaseModel):
    code: str
    discount_amount: Decimal
    amount_after_discount: Decimal