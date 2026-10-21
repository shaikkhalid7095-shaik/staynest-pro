import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RoomStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class RoomType(Base):
    __tablename__ = "room_types"
    # same hotel can't have two room types called "Deluxe"
    __table_args__ = (UniqueConstraint("hotel_id", "name", name="uq_room_type_hotel_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_adults: Mapped[int] = mapped_column(SmallInteger, default=2)
    max_children: Mapped[int] = mapped_column(SmallInteger, default=0)
    bed_type: Mapped[str | None] = mapped_column(String(30))
    size_sqft: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    hotel: Mapped["Hotel"] = relationship(back_populates="room_types")
    rooms: Mapped[list["Room"]] = relationship(back_populates="room_type")


class Room(Base):
    __tablename__ = "rooms"
    # room number 101 can exist in many hotels, but only once per hotel
    __table_args__ = (UniqueConstraint("hotel_id", "room_number", name="uq_room_hotel_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    room_type_id: Mapped[int] = mapped_column(
        ForeignKey("room_types.id", ondelete="RESTRICT"), index=True
    )
    room_number: Mapped[str] = mapped_column(String(10))
    floor: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(20), default=RoomStatus.AVAILABLE.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    hotel: Mapped["Hotel"] = relationship(back_populates="rooms")
    room_type: Mapped["RoomType"] = relationship(back_populates="rooms")
