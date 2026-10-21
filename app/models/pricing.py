from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PricingRule(Base):
    """Changes the base price on some nights.

    Examples:
      Weekend +20%      -> days_of_week="4,5"  (Fri, Sat nights), adjustment_percent=20
      Diwali season +35% -> start_date / end_date, adjustment_percent=35
      Monsoon offer -15% -> start_date / end_date, adjustment_percent=-15
    When several rules match the same night, their percentages are added.
    """

    __tablename__ = "pricing_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    # NULL = rule applies to every room type of the hotel
    room_type_id: Mapped[int | None] = mapped_column(ForeignKey("room_types.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    adjustment_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    days_of_week: Mapped[str | None] = mapped_column(String(20))  # "0,1" ... Monday=0, Sunday=6
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
