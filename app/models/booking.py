import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, SmallInteger, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BookingStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"  # created, room held for a few minutes
    CONFIRMED = "CONFIRMED"              # paid
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"                  # never paid, hold ran out


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        # every availability check searches by room + dates, so index exactly that
        Index("ix_bookings_room_dates", "room_id", "check_in", "check_out"),
        CheckConstraint("check_out > check_in", name="ck_booking_dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_code: Mapped[str] = mapped_column(String(20), unique=True)

    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="RESTRICT"), index=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id", ondelete="RESTRICT"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"))

    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    nights: Mapped[int] = mapped_column(SmallInteger)
    adults: Mapped[int] = mapped_column(SmallInteger)
    children: Mapped[int] = mapped_column(SmallInteger, default=0)

    status: Mapped[str] = mapped_column(
        String(20), default=BookingStatus.PENDING_PAYMENT.value, index=True
    )

    # prices are copied into the booking, so later price changes don't affect it
    room_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("coupons.id", ondelete="SET NULL"))

    special_requests: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime)   # day 3
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime)  # day 3
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255))
    cancelled_by: Mapped[str | None] = mapped_column(String(20))  # CUSTOMER / HOTEL / ADMIN / SYSTEM

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped["User"] = relationship()
    hotel: Mapped["Hotel"] = relationship()
    room_type: Mapped["RoomType"] = relationship()
    room: Mapped["Room"] = relationship()
    coupon: Mapped["Coupon | None"] = relationship()
    guests: Mapped[list["BookingGuest"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan", order_by="BookingGuest.id"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="booking", order_by="Payment.id")
    invoice: Mapped["Invoice | None"] = relationship(back_populates="booking", uselist=False)


class BookingGuest(Base):
    __tablename__ = "booking_guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    age: Mapped[int | None] = mapped_column(SmallInteger)
    phone: Mapped[str | None] = mapped_column(String(20))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    booking: Mapped["Booking"] = relationship(back_populates="guests")
