from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Hotel, Room, RoomStatus, RoomType
from app.schemas.booking import MAX_NIGHTS
from app.services import pricing_service
from app.utils.money import money
from app.utils.time import utcnow

UNUSABLE_ROOM_STATUSES = [RoomStatus.MAINTENANCE.value, RoomStatus.OUT_OF_SERVICE.value]


def validate_dates(check_in: date, check_out: date):
    if check_in < date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "check_in can't be in the past")
    if check_out <= check_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "check_out must be after check_in")
    if (check_out - check_in).days > MAX_NIGHTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"At most {MAX_NIGHTS} nights")


def overlaps(check_in: date, check_out: date):
    """SQL condition: a booking that blocks a room between these dates.

    Two stays overlap when one starts before the other ends:
        existing.check_in < new.check_out  AND  existing.check_out > new.check_in
    Check-out day is free for the next guest, which is why we use < and > (not <=).
    A PENDING_PAYMENT booking only blocks while its hold hasn't expired.
    """
    return and_(
        Booking.check_in < check_out,
        Booking.check_out > check_in,
        or_(
            Booking.status.in_([BookingStatus.CONFIRMED.value, BookingStatus.CHECKED_IN.value]),
            and_(
                Booking.status == BookingStatus.PENDING_PAYMENT.value,
                Booking.expires_at > utcnow(),
            ),
        ),
    )


def _free_rooms_query(room_type_id: int, check_in: date, check_out: date):
    busy_room_ids = select(Booking.room_id).where(
        Booking.room_type_id == room_type_id, overlaps(check_in, check_out)
    )
    return select(Room).where(
        Room.room_type_id == room_type_id,
        Room.is_active.is_(True),
        Room.status.notin_(UNUSABLE_ROOM_STATUSES),
        Room.id.notin_(busy_room_ids),
    )


def free_rooms(db: Session, room_type_id: int, check_in: date, check_out: date) -> list[Room]:
    query = _free_rooms_query(room_type_id, check_in, check_out).order_by(Room.room_number)
    return list(db.scalars(query))


def count_free_rooms(db: Session, room_type_id: int, check_in: date, check_out: date) -> int:
    query = _free_rooms_query(room_type_id, check_in, check_out).with_only_columns(func.count(Room.id))
    return db.scalar(query) or 0


def room_is_free(db: Session, room_id: int, check_in: date, check_out: date, ignore_booking_id: int) -> bool:
    clash = db.scalar(
        select(Booking.id)
        .where(Booking.room_id == room_id, Booking.id != ignore_booking_id, overlaps(check_in, check_out))
        .limit(1)
    )
    return clash is None


def lock_room_type(db: Session, room_type_id: int) -> RoomType | None:
    # SELECT ... FOR UPDATE: a second booking for the same room type waits here
    # until the first one commits. Together with READ COMMITTED (database.py)
    # this is what stops two people getting the same room.
    return db.scalar(select(RoomType).where(RoomType.id == room_type_id).with_for_update())


def hotel_availability(db: Session, hotel: Hotel, check_in: date, check_out: date, adults: int, children: int):
    validate_dates(check_in, check_out)
    nights = (check_out - check_in).days
    result = []

    for room_type in hotel.room_types:
        if not room_type.is_active:
            continue
        if adults > room_type.max_adults or children > room_type.max_children:
            continue
        free = count_free_rooms(db, room_type.id, check_in, check_out)
        if free == 0:
            continue
        total = pricing_service.stay_price(room_type, check_in, check_out)
        result.append({
            "room_type_id": room_type.id,
            "name": room_type.name,
            "max_adults": room_type.max_adults,
            "max_children": room_type.max_children,
            "price_per_night": money(total / nights),  # average, weekends may cost more
            "nights": nights,
            "estimated_total": total,
            "available_rooms": free,
        })

    return sorted(result, key=lambda r: r["price_per_night"])
