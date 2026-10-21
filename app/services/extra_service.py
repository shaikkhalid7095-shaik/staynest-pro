from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Hotel, HotelService, ServiceOrder, User
from app.schemas.service import OrderCreate, ServiceCreate, ServiceUpdate
from app.services import notification_service
from app.utils.money import money
from app.utils.time import utcnow

# which status can move to which
NEXT_STATUS = {
    "REQUESTED": {"IN_PROGRESS", "DELIVERED", "CANCELLED"},
    "IN_PROGRESS": {"DELIVERED", "CANCELLED"},
    "DELIVERED": set(),
    "CANCELLED": set(),
}


# ---------- catalogue ----------

def _check_name_free(db: Session, hotel_id: int, name: str, skip_id: int | None = None):
    existing = db.scalar(select(HotelService).where(HotelService.hotel_id == hotel_id, HotelService.name == name))
    if existing and existing.id != skip_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{name}' already exists in this hotel")


def create_service(db: Session, hotel: Hotel, data: ServiceCreate) -> HotelService:
    _check_name_free(db, hotel.id, data.name)
    service = HotelService(**data.model_dump(), hotel_id=hotel.id)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


def list_services(db: Session, hotel: Hotel, only_active: bool) -> list[HotelService]:
    query = select(HotelService).where(HotelService.hotel_id == hotel.id)
    if only_active:
        query = query.where(HotelService.is_active.is_(True))
    return list(db.scalars(query.order_by(HotelService.category, HotelService.name)))


def get_service(db: Session, hotel: Hotel, service_id: int) -> HotelService:
    service = db.get(HotelService, service_id)
    if service is None or service.hotel_id != hotel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service not found")
    return service


def update_service(db: Session, service: HotelService, data: ServiceUpdate) -> HotelService:
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _check_name_free(db, service.hotel_id, changes["name"], skip_id=service.id)
    for field, value in changes.items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return service


# ---------- orders ----------

def place_order(db: Session, booking: Booking, data: OrderCreate, user: User) -> ServiceOrder:
    if booking.customer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the guest can order services")

    service = db.get(HotelService, data.service_id)
    if service is None or service.hotel_id != booking.hotel_id or not service.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This hotel doesn't offer that service")

    if booking.status not in (BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Can't add services to a {booking.status} booking")
    if service.category == "ROOM_SERVICE" and booking.status != BookingStatus.CHECKED_IN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Room service is only available after check-in")

    order = ServiceOrder(
        booking_id=booking.id,
        service_id=service.id,
        quantity=data.quantity,
        unit_price=service.price,
        total_price=money(service.price * data.quantity),
        notes=data.notes,
    )
    db.add(order)
    notification_service.notify(
        db, booking.hotel.owner_id, f"New order: {service.name}",
        f"Room {booking.room.room_number} ordered {data.quantity} x {service.name}.",
        type="SERVICE", reference=f"booking:{booking.id}",
    )
    db.commit()
    db.refresh(order)
    return order


def list_booking_orders(db: Session, booking: Booking) -> list[ServiceOrder]:
    return list(db.scalars(select(ServiceOrder).where(ServiceOrder.booking_id == booking.id).order_by(ServiceOrder.id)))


def list_hotel_orders(db: Session, hotel: Hotel, order_status: str | None, category: str | None) -> list[ServiceOrder]:
    query = (
        select(ServiceOrder)
        .join(Booking, ServiceOrder.booking_id == Booking.id)
        .join(HotelService, ServiceOrder.service_id == HotelService.id)
        .where(Booking.hotel_id == hotel.id)
    )
    if order_status:
        query = query.where(ServiceOrder.status == order_status)
    if category:
        query = query.where(HotelService.category == category)
    return list(db.scalars(query.order_by(ServiceOrder.requested_at)))


def get_order(db: Session, order_id: int) -> ServiceOrder:
    order = db.get(ServiceOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def change_status(db: Session, order: ServiceOrder, new_status: str) -> ServiceOrder:
    if new_status not in NEXT_STATUS[order.status]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Can't move an order from {order.status} to {new_status}")

    order.status = new_status
    if new_status == "DELIVERED":
        order.delivered_at = utcnow()

    notification_service.notify(
        db, order.booking.customer_id, f"{order.service.name}: {new_status.replace('_', ' ').lower()}",
        f"Your order for {order.quantity} x {order.service.name} is now {new_status}.",
        type="SERVICE", reference=f"booking:{order.booking_id}",
    )
    db.commit()
    db.refresh(order)
    return order


def cancel_by_guest(db: Session, order: ServiceOrder, user: User) -> ServiceOrder:
    if order.booking.customer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your order")
    if order.status != "REQUESTED":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The hotel already started this order")
    order.status = "CANCELLED"
    db.commit()
    db.refresh(order)
    return order
