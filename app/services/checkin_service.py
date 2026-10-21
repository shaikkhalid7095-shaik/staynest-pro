from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Hotel, RoomStatus, ServiceOrder
from app.services import availability_service, housekeeping_service, loyalty_service, notification_service
from app.utils.money import money
from app.utils.time import utcnow


def check_in(db: Session, booking: Booking) -> Booking:
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Only CONFIRMED bookings can check in (this one is {booking.status})")

    today = date.today()
    if today < booking.check_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Too early - check-in date is {booking.check_in}")
    if today >= booking.check_out:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This stay has already ended")

    room = booking.room
    if room.status != RoomStatus.AVAILABLE:
        # the booked room is busy or broken - move the guest to another free room of the same type
        others = [
            r for r in availability_service.free_rooms(db, booking.room_type_id, today, booking.check_out)
            if r.status == RoomStatus.AVAILABLE and r.id != room.id
        ]
        if not others:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Room {room.room_number} is {room.status} and no other room is free")
        room = others[0]
        booking.room_id = room.id
        booking.room = room

    booking.status = BookingStatus.CHECKED_IN.value
    booking.checked_in_at = utcnow()
    room.status = RoomStatus.OCCUPIED.value

    notification_service.notify(
        db, booking.customer_id, "Welcome!",
        f"You are checked in to room {room.room_number} at {booking.hotel.name}. Enjoy your stay.",
        type="STAY", reference=f"booking:{booking.id}",
    )
    db.commit()
    db.refresh(booking)
    return booking


def check_out(db: Session, booking: Booking) -> dict:
    if booking.status != BookingStatus.CHECKED_IN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Only CHECKED_IN bookings can check out (this one is {booking.status})")

    orders = list(db.scalars(
        select(ServiceOrder).where(ServiceOrder.booking_id == booking.id, ServiceOrder.status != "CANCELLED")
    ))
    if any(o.status in ("REQUESTED", "IN_PROGRESS") for o in orders):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Some service orders are still open. Deliver or cancel them first")

    extras_total = money(sum((o.total_price for o in orders), Decimal("0")))
    collected_now = money(sum((o.total_price for o in orders if not o.is_paid), Decimal("0")))
    for order in orders:
        order.is_paid = True  # extras are paid at the front desk

    booking.status = BookingStatus.CHECKED_OUT.value
    booking.checked_out_at = utcnow()
    booking.room.status = RoomStatus.AVAILABLE.value
    db.add(housekeeping_service.cleaning_after_checkout(booking.hotel_id, booking.room_id, booking.id))
    points = loyalty_service.earn_for_booking(db, booking)  # day 4

    notification_service.notify(
        db, booking.customer_id, "Thanks for staying with us",
        f"You have checked out of {booking.hotel.name} and earned {points} loyalty points. "
        "We'd love a review of your stay!",
        type="STAY", reference=f"booking:{booking.id}",
    )
    db.commit()
    db.refresh(booking)

    return {
        "booking": booking,
        "room_charges": booking.total_amount,
        "extras_total": extras_total,
        "extras_collected_now": collected_now,
        "grand_total": money(booking.total_amount + extras_total),
        "loyalty_points_earned": points,
    }


def arrivals(db: Session, hotel: Hotel, day: date) -> list[Booking]:
    return list(db.scalars(
        select(Booking).where(
            Booking.hotel_id == hotel.id, Booking.check_in == day,
            Booking.status == BookingStatus.CONFIRMED.value,
        ).order_by(Booking.id)
    ))


def departures(db: Session, hotel: Hotel, day: date) -> list[Booking]:
    return list(db.scalars(
        select(Booking).where(
            Booking.hotel_id == hotel.id, Booking.check_out == day,
            Booking.status == BookingStatus.CHECKED_IN.value,
        ).order_by(Booking.id)
    ))


def in_house(db: Session, hotel: Hotel) -> list[Booking]:
    return list(db.scalars(
        select(Booking).where(Booking.hotel_id == hotel.id, Booking.status == BookingStatus.CHECKED_IN.value)
    ))
