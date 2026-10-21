from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_NIGHTS = 30


class GuestIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    age: int | None = Field(default=None, ge=0, le=120)
    phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")
    is_primary: bool = False


class GuestOut(GuestIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BookingCreate(BaseModel):
    hotel_id: int
    room_type_id: int
    check_in: date
    check_out: date
    adults: int = Field(ge=1, le=10)
    children: int = Field(default=0, ge=0, le=10)
    guests: list[GuestIn] = []
    coupon_code: str | None = Field(default=None, max_length=30)
    special_requests: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check_dates_and_guests(self):
        # runs after each field is validated, so we can compare fields with each other
        if self.check_in < date.today():
            raise ValueError("check_in can't be in the past")
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        if (self.check_out - self.check_in).days > MAX_NIGHTS:
            raise ValueError(f"You can book at most {MAX_NIGHTS} nights")
        if len(self.guests) > self.adults + self.children:
            raise ValueError("More guest names than adults + children")
        return self


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_code: str
    customer_id: int
    hotel_id: int
    room_type_id: int
    room_id: int
    check_in: date
    check_out: date
    nights: int
    adults: int
    children: int
    status: str
    room_rate: Decimal
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    special_requests: str | None
    expires_at: datetime | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    guests: list[GuestOut]


class GuestsUpdate(BaseModel):
    guests: list[GuestIn] = Field(min_length=1)


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class RefundQuote(BaseModel):
    booking_id: int
    paid_amount: Decimal
    refund_percent: int
    refund_amount: Decimal
    policy: str


class CancelResponse(BaseModel):
    booking: BookingOut
    refund_amount: Decimal
    refund_status: str | None