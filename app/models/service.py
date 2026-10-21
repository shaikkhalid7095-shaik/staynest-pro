from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class HotelService(Base):
    # things a hotel sells on top of the room: breakfast, spa, airport pickup, room service food
    __tablename__ = "hotel_services"
    __table_args__ = (UniqueConstraint("hotel_id", "name", name="uq_service_hotel_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # ROOM_SERVICE needs the guest to be checked in; the rest can be booked in advance
    category: Mapped[str] = mapped_column(String(20))  # ROOM_SERVICE / SPA / TRANSPORT / LAUNDRY / FOOD / OTHER
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("hotel_services.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(SmallInteger, default=1)
    # price copied at order time, like in bookings
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="REQUESTED", index=True)
    notes: Mapped[str | None] = mapped_column(String(255))
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # settled at check-out
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)

    service: Mapped["HotelService"] = relationship()
    booking: Mapped["Booking"] = relationship()
