from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.booking import BookingOut

Category = Literal["ROOM_SERVICE", "SPA", "TRANSPORT", "LAUNDRY", "FOOD", "OTHER"]
OrderStatus = Literal["REQUESTED", "IN_PROGRESS", "DELIVERED", "CANCELLED"]


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    category: Category
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    is_active: bool | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    name: str
    description: str | None
    category: str
    price: Decimal
    is_active: bool


class OrderCreate(BaseModel):
    service_id: int
    quantity: int = Field(default=1, ge=1, le=20)
    notes: str | None = Field(default=None, max_length=255)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderOut(BaseModel):
    id: int
    booking_id: int
    service_id: int
    service_name: str
    category: str
    room_number: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    status: str
    notes: str | None
    is_paid: bool
    requested_at: datetime
    delivered_at: datetime | None

    @classmethod
    def from_row(cls, order):
        return cls(
            id=order.id, booking_id=order.booking_id, service_id=order.service_id,
            service_name=order.service.name, category=order.service.category,
            room_number=order.booking.room.room_number, quantity=order.quantity,
            unit_price=order.unit_price, total_price=order.total_price, status=order.status,
            notes=order.notes, is_paid=order.is_paid,
            requested_at=order.requested_at, delivered_at=order.delivered_at,
        )


class CheckOutSummary(BaseModel):
    booking: BookingOut
    room_charges: Decimal
    extras_total: Decimal
    extras_collected_now: Decimal
    grand_total: Decimal
    loyalty_points_earned: int = 0
