from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CreateIntentRequest(BaseModel):
    booking_id: int


class CreateIntentResponse(BaseModel):
    payment_id: int
    payment_intent_id: str
    client_secret: str  # a frontend gives this to Stripe.js to show the card form
    amount: Decimal
    currency: str


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    status: str
    reason: str | None
    created_at: datetime


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    amount: Decimal
    currency: str
    provider: str
    provider_payment_id: str | None
    status: str
    failure_reason: str | None
    created_at: datetime
    refunds: list[RefundOut]


class TestConfirmResponse(BaseModel):
    payment_id: int
    stripe_status: str
    booking_status: str


class InvoiceOut(BaseModel):
    invoice_number: str
    issued_at: datetime
    booking_code: str
    customer_name: str
    customer_email: str
    hotel_name: str
    hotel_address: str
    room_type: str
    room_number: str
    check_in: date
    check_out: date
    nights: int
    room_rate: Decimal
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    payment_status: str