import enum
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Numeric, SmallInteger, String, Table, Text, Time, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class HotelStatus(str, enum.Enum):
    PENDING = "PENDING"        # just registered, waiting for admin
    APPROVED = "APPROVED"      # visible to customers
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"    # blocked later by admin


hotel_amenities = Table(
    "hotel_amenities",
    Base.metadata,
    Column("hotel_id", ForeignKey("hotels.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    property_type: Mapped[str] = mapped_column(String(20), default="HOTEL")
    star_rating: Mapped[int | None] = mapped_column(SmallInteger)

    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))

    address_line: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), index=True)
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100), default="India")
    postal_code: Mapped[str | None] = mapped_column(String(20))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    check_in_time: Mapped[time] = mapped_column(Time, default=time(14, 0))
    check_out_time: Mapped[time] = mapped_column(Time, default=time(11, 0))

    status: Mapped[str] = mapped_column(String(20), default=HotelStatus.PENDING.value, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="hotels")
    branches: Mapped[list["HotelBranch"]] = relationship(
        back_populates="hotel", cascade="all, delete-orphan"
    )
    amenities: Mapped[list["Amenity"]] = relationship(secondary=hotel_amenities)
    room_types: Mapped[list["RoomType"]] = relationship(
        back_populates="hotel", cascade="all, delete-orphan"
    )
    rooms: Mapped[list["Room"]] = relationship(back_populates="hotel", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Hotel {self.name}>"


class HotelBranch(Base):
    __tablename__ = "hotel_branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    address_line: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    hotel: Mapped["Hotel"] = relationship(back_populates="branches")


class Amenity(Base):
    __tablename__ = "amenities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(30), default="GENERAL")
