from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models import RoleName, User
from app.schemas.service import (
    Category, OrderCreate, OrderOut, OrderStatus, OrderStatusUpdate, ServiceCreate, ServiceOut, ServiceUpdate,
)
from app.services import booking_service, extra_service, hotel_service, staff_service

router = APIRouter(tags=["Hotel Services & Room Service"])

owner_or_admin = require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)


@router.get("/hotels/{hotel_id}/services", response_model=list[ServiceOut])
def list_services(hotel_id: int, db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    return extra_service.list_services(db, hotel, only_active=True)


@router.post("/hotels/{hotel_id}/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(hotel_id: int, data: ServiceCreate, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return extra_service.create_service(db, hotel, data)


@router.put("/hotels/{hotel_id}/services/{service_id}", response_model=ServiceOut)
def update_service(
    hotel_id: int, service_id: int, data: ServiceUpdate,
    user: User = Depends(owner_or_admin), db: Session = Depends(get_db),
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return extra_service.update_service(db, extra_service.get_service(db, hotel, service_id), data)


@router.post("/bookings/{booking_id}/services", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def order_service(
    booking_id: int, data: OrderCreate,
    user: User = Depends(require_roles(RoleName.CUSTOMER)), db: Session = Depends(get_db),
):
    booking = booking_service.get_booking_for_user(db, booking_id, user)
    return OrderOut.from_row(extra_service.place_order(db, booking, data, user))


@router.get("/bookings/{booking_id}/services", response_model=list[OrderOut])
def booking_orders(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = booking_service.get_booking_for_user(db, booking_id, user)
    return [OrderOut.from_row(o) for o in extra_service.list_booking_orders(db, booking)]


@router.get("/hotels/{hotel_id}/service-orders", response_model=list[OrderOut])
def hotel_orders(
    hotel_id: int,
    order_status: OrderStatus | None = None,
    category: Category | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # kitchen / front desk queue. category=ROOM_SERVICE gives the room service queue
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    return [OrderOut.from_row(o) for o in extra_service.list_hotel_orders(db, hotel, order_status, category)]


@router.patch("/service-orders/{order_id}/status", response_model=OrderOut)
def change_order_status(
    order_id: int, data: OrderStatusUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if user.role.name == RoleName.CUSTOMER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Guests can only cancel - use /service-orders/{id}/cancel")
    order = extra_service.get_order(db, order_id)
    staff_service.get_operable_hotel(db, order.booking.hotel_id, user)
    return OrderOut.from_row(extra_service.change_status(db, order, data.status))


@router.post("/service-orders/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: int, user: User = Depends(require_roles(RoleName.CUSTOMER)), db: Session = Depends(get_db)):
    order = extra_service.get_order(db, order_id)
    return OrderOut.from_row(extra_service.cancel_by_guest(db, order, user))
