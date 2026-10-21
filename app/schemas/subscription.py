from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    price_monthly: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    max_hotels: int = Field(ge=1, le=1000)
    features: str | None = None


class PlanUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    price_monthly: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    max_hotels: int | None = Field(default=None, ge=1, le=1000)
    features: str | None = None
    is_active: bool | None = None


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    price_monthly: Decimal
    max_hotels: int
    features: str | None
    is_active: bool


class SubscribeRequest(BaseModel):
    plan_id: int


class SubscriptionPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    status: str
    provider_payment_id: str | None
    created_at: datetime


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    plan: PlanOut
    status: str
    start_date: date | None
    end_date: date | None
    auto_renew: bool
    created_at: datetime
    payments: list[SubscriptionPaymentOut]


class SubscribeResponse(BaseModel):
    subscription: SubscriptionOut
    client_secret: str | None  # None for free plans


class MyPlanOut(BaseModel):
    plan_name: str
    max_hotels: int
    hotels_used: int
    subscription: SubscriptionOut | None
