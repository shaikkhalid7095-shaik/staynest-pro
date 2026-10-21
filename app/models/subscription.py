from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SubscriptionPlan(Base):
    # what hotel owners pay the platform every month
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    price_monthly: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_hotels: Mapped[int] = mapped_column(SmallInteger)
    features: Mapped[str | None] = mapped_column(Text)  # comma separated list, shown to owners
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HotelSubscription(Base):
    __tablename__ = "hotel_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("subscription_plans.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING / ACTIVE / CANCELLED / EXPIRED
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    plan: Mapped["SubscriptionPlan"] = relationship()
    payments: Mapped[list["SubscriptionPayment"]] = relationship(
        back_populates="subscription", order_by="SubscriptionPayment.id"
    )


class SubscriptionPayment(Base):
    __tablename__ = "subscription_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("hotel_subscriptions.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="inr")
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING / SUCCEEDED / FAILED
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    subscription: Mapped["HotelSubscription"] = relationship(back_populates="payments")
