from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import UserOut


class UserPage(BaseModel):
    total: int
    page: int
    size: int
    items: list[UserOut]


class UserStatusUpdate(BaseModel):
    is_active: bool
    reason: str | None = Field(default=None, max_length=255)


class AdminCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=64)


class HotelModeration(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    action: str
    entity: str | None
    entity_id: int | None
    details: str | None
    ip_address: str | None
    created_at: datetime


class FraudFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int | None
    user_id: int | None
    score: int
    reasons: str
    status: str
    review_note: str | None
    reviewed_by_id: int | None
    created_at: datetime


class FraudReview(BaseModel):
    status: Literal["CONFIRMED_FRAUD", "DISMISSED"]
    note: str | None = Field(default=None, max_length=255)
    block_user: bool = False


class SettingOut(BaseModel):
    key: str
    value: str
    default: str
    type: str
    description: str
    is_public: bool
    updated_at: datetime | None


class SettingUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=255)


class LoyaltyTxnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    points: int
    type: str
    note: str | None
    booking_id: int | None
    created_at: datetime


class LoyaltySummary(BaseModel):
    points: int
    lifetime_points: int
    tier: str
    next_tier: str | None
    points_to_next_tier: int
    history: list[LoyaltyTxnOut]


class RedeemRequest(BaseModel):
    points: int = Field(ge=1)


class RedeemResponse(BaseModel):
    coupon_code: str
    value: Decimal
    points_used: int
    points_left: int
    valid_until: datetime


class LoyaltyAdjust(BaseModel):
    user_id: int
    points: int = Field(description="Positive to add, negative to take away")
    note: str = Field(min_length=3, max_length=255)


class PayoutCreate(BaseModel):
    hotel_id: int
    period_start: date
    period_end: date


class PayoutPaid(BaseModel):
    reference: str = Field(min_length=3, max_length=100)


class PayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    period_start: date
    period_end: date
    bookings_count: int
    gross_amount: Decimal
    commission_amount: Decimal
    net_amount: Decimal
    status: str
    reference: str | None
    paid_at: datetime | None
    created_at: datetime
