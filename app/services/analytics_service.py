"""31-33 analytics and 47 business intelligence.

Everything here only reads existing tables (bookings, rooms, payments).
Numbers are added up in Python instead of SQL date functions, so the same
code works on MySQL and on the SQLite database the tests use.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Hotel, Room, RoleName, User
from app.services import booking_service
from app.utils.money import money

PAID = [BookingStatus.CONFIRMED.value, BookingStatus.CHECKED_IN.value, BookingStatus.CHECKED_OUT.value]


# ---------- which hotels can this user see ----------

def hotel_ids_for(db: Session, user: User, hotel_id: int | None) -> list[int]:
    if user.role.name == RoleName.ADMIN:
        if hotel_id:
            return [hotel_id]
        return list(db.scalars(select(Hotel.id)))
    own = list(db.scalars(select(Hotel.id).where(Hotel.owner_id == user.id)))
    if hotel_id:
        if hotel_id not in own:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your hotel")
        return [hotel_id]
    return own


def check_range(start: date, end: date):
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end must be on or after start")
    if (end - start).days > 366:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick a range of one year or less")


def _bookings(db: Session, hotel_ids: list[int], start: date, end: date, statuses=None) -> list[Booking]:
    if not hotel_ids:
        return []
    query = select(Booking).where(Booking.hotel_id.in_(hotel_ids), Booking.check_in >= start, Booking.check_in <= end)
    if statuses:
        query = query.where(Booking.status.in_(statuses))
    return list(db.scalars(query))


def _kept_amount(b: Booking) -> Decimal:
    # a cancelled booking still earns whatever wasn't refunded (late-cancellation fee)
    if b.status in PAID:
        return b.total_amount
    if b.status == BookingStatus.CANCELLED:
        return booking_service.amount_paid(b)
    return Decimal("0")


# ---------- 31. revenue ----------

def revenue(db: Session, hotel_ids: list[int], start: date, end: date, group_by: str) -> dict:
    bookings = _bookings(db, hotel_ids, start, end, PAID + [BookingStatus.CANCELLED.value])
    buckets = defaultdict(lambda: {"bookings": 0, "room_revenue": Decimal("0"), "tax": Decimal("0"), "total": Decimal("0")})

    for b in bookings:
        kept = _kept_amount(b)
        if kept == 0:
            continue
        key = b.check_in.strftime("%Y-%m") if group_by == "month" else b.check_in.isoformat()
        row = buckets[key]
        if b.status in PAID:
            row["bookings"] += 1
            row["room_revenue"] += b.subtotal - b.discount_amount
            row["tax"] += b.tax_amount
        else:
            row["room_revenue"] += kept  # cancellation fee counts as room income
        row["total"] += kept

    series = [{"period": k, **{f: (money(v) if isinstance(v, Decimal) else v) for f, v in row.items()}}
              for k, row in sorted(buckets.items())]
    return {
        "start": start, "end": end, "group_by": group_by,
        "total_bookings": sum(r["bookings"] for r in series),
        "total_room_revenue": money(sum((r["room_revenue"] for r in series), Decimal("0"))),
        "total_tax": money(sum((r["tax"] for r in series), Decimal("0"))),
        "total_revenue": money(sum((r["total"] for r in series), Decimal("0"))),
        "series": series,
    }


# ---------- 32. occupancy ----------

def occupancy(db: Session, hotel_ids: list[int], start: date, end: date) -> dict:
    if not hotel_ids:
        hotel_ids = [-1]  # nothing to show, but keep the same response shape
    rooms = db.scalar(
        select(func.count(Room.id)).where(Room.hotel_id.in_(hotel_ids), Room.is_active.is_(True))
    ) or 0

    # bookings that touch the range at all
    stays = list(db.scalars(select(Booking).where(
        Booking.hotel_id.in_(hotel_ids), Booking.status.in_(PAID),
        Booking.check_in <= end, Booking.check_out > start,
    )))

    series, sold, room_income = [], 0, Decimal("0")
    day = start
    while day <= end:
        occupied = [b for b in stays if b.check_in <= day < b.check_out]
        sold += len(occupied)
        room_income += sum((b.room_rate for b in occupied), Decimal("0"))
        rate = round(len(occupied) / rooms * 100, 1) if rooms else 0.0
        series.append({"date": day, "rooms_sold": len(occupied), "total_rooms": rooms, "occupancy_percent": rate})
        day += timedelta(days=1)

    available = rooms * len(series)
    adr = money(room_income / sold) if sold else Decimal("0.00")       # average daily rate
    revpar = money(room_income / available) if available else Decimal("0.00")  # revenue per available room
    return {
        "start": start, "end": end, "total_rooms": rooms,
        "room_nights_sold": sold, "room_nights_available": available,
        "occupancy_percent": round(sold / available * 100, 1) if available else 0.0,
        "adr": adr, "revpar": revpar, "series": series,
    }
