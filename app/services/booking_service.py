import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Booking, BookingGuest, BookingStatus, Hotel, PaymentStatus, RoleName, User,
)
from app.schemas.booking import BookingCreate, GuestIn
from app.services import (
    availability_service, hotel_service, notification_service, payment_service, pricing_service, staff_service,
)
from app.utils.money import money
from app.utils.time import utcnow

HOLD_MINUTES = 15  # how long an unpaid booking keeps the room


def _new_booking_code(db: Session) -> str:
    while True:
        code = "SN" + secrets.token_hex(4).upper()  # e.g. SN9F3A1C2B
        if not db.scalar(select(Booking.id).where(Booking.booking_code == code)):
            return code


def create_booking(db: Session, data: BookingCreate, customer: User) -> Booking:
    hotel = hotel_service.get_public_hotel(db, data.hotel_id)

    # lock first, check second - see lock_room_type() for why
    room_type = availability_service.lock_room_type(db, data.room_type_id)
    if room_type is None or room_type.hotel_id != hotel.id or not room_type.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room type not found in this hotel")

    if data.adults > room_type.max_adults or data.children > room_type.max_children:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{room_type.name} allows {room_type.max_adults} adults and {room_type.max_children} children",
        )

    rooms = availability_service.free_rooms(db, room_type.id, data.check_in, data.check_out)
    if not rooms:
        raise HTTPException(status.HTTP_409_CONFLICT, "No rooms of this type are free for these dates")
    room = rooms[0]

    nights = (data.check_out - data.check_in).days
    # day 3: every night is priced on its own (weekend / season rules)
    subtotal = pricing_service.stay_price(room_type, data.check_in, data.check_out)

    coupon, discount = None, Decimal("0")
    if data.coupon_code:
        coupon, discount = pricing_service.coupon_discount(db, data.coupon_code, hotel.id, customer.id, subtotal)
    prices = pricing_service.calculate(subtotal, nights, discount)

    booking = Booking(
        booking_code=_new_booking_code(db),
        customer_id=customer.id,
        hotel_id=hotel.id,
        room_type_id=room_type.id,
        room_id=room.id,
        check_in=data.check_in,
        check_out=data.check_out,
        nights=nights,
        adults=data.adults,
        children=data.children,
        coupon_id=coupon.id if coupon else None,
        special_requests=data.special_requests,
        status=BookingStatus.PENDING_PAYMENT.value,
        expires_at=utcnow() + timedelta(minutes=HOLD_MINUTES),
        **prices,
    )
    booking.guests = _build_guests(data.guests, customer)

    db.add(booking)
    db.commit()  # commit also releases the room-type lock
    db.refresh(booking)
    return booking


def _build_guests(guests: list[GuestIn], customer: User) -> list[BookingGuest]:
    if not guests:
        # no names given: the customer is the guest
        return [BookingGuest(full_name=customer.full_name, phone=customer.phone, is_primary=True)]

    rows = [BookingGuest(**g.model_dump()) for g in guests]
    primaries = [r for r in rows if r.is_primary]
    if len(primaries) > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only one guest can be primary")
    if not primaries:
        rows[0].is_primary = True
    return rows


def expire_if_needed(db: Session, booking: Booking):
    if (
        booking.status == BookingStatus.PENDING_PAYMENT
        and booking.expires_at is not None
        and booking.expires_at < utcnow()
    ):
        booking.status = BookingStatus.EXPIRED.value
        db.commit()


def get_booking_for_user(db: Session, booking_id: int, user: User) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    role = user.role.name
    allowed = (
        role == RoleName.ADMIN
        or (role == RoleName.CUSTOMER and booking.customer_id == user.id)
        or (role == RoleName.HOTEL_OWNER and booking.hotel.owner_id == user.id)
        or (role == RoleName.HOTEL_STAFF and staff_service.works_at(db, user, booking.hotel_id))
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't view this booking")

    expire_if_needed(db, booking)
    return booking


def list_customer_bookings(db: Session, user: User, booking_status: str | None) -> list[Booking]:
    query = select(Booking).where(Booking.customer_id == user.id)
    if booking_status:
        query = query.where(Booking.status == booking_status)
    return list(db.scalars(query.order_by(Booking.id.desc())))


def list_hotel_bookings(
    db: Session, hotel: Hotel, booking_status: str | None, date_from: date | None, date_to: date | None
) -> list[Booking]:
    query = select(Booking).where(Booking.hotel_id == hotel.id)
    if booking_status:
        query = query.where(Booking.status == booking_status)
    if date_from:
        query = query.where(Booking.check_out > date_from)
    if date_to:
        query = query.where(Booking.check_in < date_to)
    return list(db.scalars(query.order_by(Booking.check_in)))


def replace_guests(db: Session, booking: Booking, guests: list[GuestIn], user: User) -> Booking:
    if booking.customer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the customer who booked can change guests")
    if booking.status not in (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Can't change guests of a {booking.status} booking")
    if len(guests) > booking.adults + booking.children:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "More guests than adults + children on the booking")

    booking.guests = _build_guests(guests, user)  # delete-orphan removes the old rows
    db.commit()
    db.refresh(booking)
    return booking


# ---------- cancellation & refund ----------

def amount_paid(booking: Booking) -> Decimal:
    paid = Decimal("0")
    for p in booking.payments:
        if p.status in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED):
            paid += p.amount
            paid -= sum((r.amount for r in p.refunds if r.status != "FAILED"), Decimal("0"))
    return money(paid)


def refund_quote(booking: Booking, by_hotel: bool) -> dict:
    paid = amount_paid(booking)

    if paid == 0:
        percent, policy = 0, "Nothing has been paid"
    elif by_hotel:
        percent, policy = 100, "Cancelled by the hotel or admin: full refund"
    else:
        check_in_at = datetime.combine(booking.check_in, booking.hotel.check_in_time)
        hours_left = (check_in_at - datetime.now()).total_seconds() / 3600
        if hours_left >= 48:
            percent, policy = 100, "48+ hours before check-in: full refund"
        elif hours_left >= 24:
            percent, policy = 50, "24-48 hours before check-in: 50% refund"
        else:
            percent, policy = 0, "Less than 24 hours before check-in: no refund"

    return {
        "booking_id": booking.id,
        "paid_amount": paid,
        "refund_percent": percent,
        "refund_amount": money(paid * percent / 100),
        "policy": policy,
    }


def cancel_booking(db: Session, booking: Booking, user: User, reason: str | None) -> dict:
    if booking.status not in (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A {booking.status} booking can't be cancelled")

    role = user.role.name
    by_hotel = role != RoleName.CUSTOMER
    quote = refund_quote(booking, by_hotel)

    refund = None
    if quote["refund_amount"] > 0:
        # Stripe first: if Stripe fails we raise and the booking stays as it was
        refund = payment_service.refund_booking(db, booking, quote["refund_amount"], reason or "Booking cancelled")

    booking.status = BookingStatus.CANCELLED.value
    booking.cancelled_at = utcnow()
    booking.cancellation_reason = reason
    booking.cancelled_by = "CUSTOMER" if role == RoleName.CUSTOMER else ("ADMIN" if role == RoleName.ADMIN else "HOTEL")

    refund_text = f" Refund of Rs {quote['refund_amount']} is on its way." if quote["refund_amount"] > 0 else ""
    notification_service.notify(
        db, booking.customer_id, "Booking cancelled",
        f"Booking {booking.booking_code} was cancelled.{refund_text}",
        type="BOOKING", reference=f"booking:{booking.id}",
    )
    if role == RoleName.CUSTOMER:
        notification_service.notify(
            db, booking.hotel.owner_id, "Booking cancelled by guest",
            f"Booking {booking.booking_code} ({booking.check_in} to {booking.check_out}) was cancelled.",
            type="BOOKING", reference=f"booking:{booking.id}",
        )
    db.commit()
    db.refresh(booking)

    return {
        "booking": booking,
        "refund_amount": quote["refund_amount"],
        "refund_status": refund.status if refund else None,
    }
