from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class HotelStaff(Base):
    __tablename__ = "hotel_staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique: one staff account works at one hotel
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    position: Mapped[str] = mapped_column(String(50))  # RECEPTION, HOUSEKEEPING, KITCHEN, MANAGER
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship()


class HousekeepingTask(Base):
    __tablename__ = "housekeeping_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"))
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    task_type: Mapped[str] = mapped_column(String(20))  # CLEANING / INSPECTION / MAINTENANCE / LAUNDRY
    priority: Mapped[str] = mapped_column(String(10), default="NORMAL")  # LOW / NORMAL / HIGH
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)  # PENDING / IN_PROGRESS / DONE
    notes: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    room: Mapped["Room"] = relationship()
