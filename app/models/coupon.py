from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))

    discount_type: Mapped[str] = mapped_column(String(10))  # PERCENT or FLAT
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_discount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # cap for PERCENT coupons
    min_booking_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_until: Mapped[datetime] = mapped_column(DateTime)

    usage_limit: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1)

    # NULL hotel_id = works on every hotel (platform coupon from admin)
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())