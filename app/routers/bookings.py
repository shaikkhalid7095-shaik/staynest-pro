from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models import BookingStatus, RoleName, User
from app.schemas.booking import (
    BookingCreate, BookingOut, CancelRequest, CancelResponse, GuestOut, GuestsUpdate, RefundQuote,
)
from app.schemas.payment import InvoiceOut
from app.services import booking_service, fraud_service, hotel_service, payment_service

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    data: BookingCreate,
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    booking = booking_service.create_booking(db, data, user)
    fraud_service.screen_booking(db, booking)  # day 4: flags it for admin review, never blocks
    return booking


# fixed paths ("/my", "/hotel/...") come before "/{booking_id}"
@router.get("/my", response_model=list[BookingOut])
def my_bookings(
    booking_status: BookingStatus | None = None,
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    return booking_service.list_customer_bookings(db, user, booking_status.value if booking_status else None)


@router.get("/hotel/{hotel_id}", response_model=list[BookingOut])
def hotel_bookings(
    hotel_id: int,
    booking_status: BookingStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return booking_service.list_hotel_bookings(
        db, hotel, booking_status.value if booking_status else None, date_from, date_to
    )


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return booking_service.get_booking_for_user(db, booking_id, user)


@router.get("/{booking_id}/guests", response_model=list[GuestOut])
def get_guests(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return booking_service.get_booking_for_user(db, booking_id, user).guests


@router.put("/{booking_id}/guests", response_model=BookingOut)
def update_guests(
    booking_id: int,
    data: GuestsUpdate,
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    booking = booking_service.get_booking_for_user(db, booking_id, user)
    return booking_service.replace_guests(db, booking, data.guests, user)


@router.get("/{booking_id}/refund-quote", response_model=RefundQuote)
def refund_quote(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = booking_service.get_booking_for_user(db, booking_id, user)
    return booking_service.refund_quote(booking, by_hotel=user.role.name != RoleName.CUSTOMER)


@router.post("/{booking_id}/cancel", response_model=CancelResponse)
def cancel_booking(
    booking_id: int, data: CancelRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    booking = booking_service.get_booking_for_user(db, booking_id, user)
    return booking_service.cancel_booking(db, booking, user, data.reason)


@router.get("/{booking_id}/invoice", response_model=InvoiceOut)
def get_invoice(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = booking_service.get_booking_for_user(db, booking_id, user)
    return payment_service.invoice_data(booking)
