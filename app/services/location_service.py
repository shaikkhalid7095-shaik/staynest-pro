"""44 location services and 45 calendar / booking scheduler."""

import math
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, Hotel, HotelStatus, Room, RoomStatus, RoomType
from app.services import availability_service, pricing_service
from app.services.analytics_service import PAID

EARTH_RADIUS_KM = 6371


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    # haversine formula: straight-line distance over the earth's surface
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a)), 2)


def _public_hotels(db: Session):
    return select(Hotel).where(Hotel.status == HotelStatus.APPROVED.value, Hotel.is_active.is_(True))


def nearby(db: Session, lat: float, lng: float, radius_km: float, limit: int) -> list[dict]:
    hotels = db.scalars(_public_hotels(db).where(Hotel.latitude.is_not(None), Hotel.longitude.is_not(None)))
    found = []
    for h in hotels:
        km = distance_km(lat, lng, float(h.latitude), float(h.longitude))
        if km <= radius_km:
            found.append({"hotel_id": h.id, "name": h.name, "city": h.city, "star_rating": h.star_rating,
                          "latitude": h.latitude, "longitude": h.longitude, "distance_km": km})
    return sorted(found, key=lambda x: x["distance_km"])[:limit]


def cities(db: Session) -> list[dict]:
    rows = db.execute(
        _public_hotels(db).with_only_columns(Hotel.city, func.count(Hotel.id)).group_by(Hotel.city).order_by(Hotel.city)
    ).all()
    return [{"city": c, "hotels": n} for c, n in rows]


# ---------- 45. calendar ----------

def room_calendar(db: Session, hotel: Hotel, start: date, days: int) -> list[dict]:
    end = start + timedelta(days=days)
    rooms = list(db.scalars(select(Room).where(Room.hotel_id == hotel.id, Room.is_active.is_(True)).order_by(Room.room_number)))
    stays = list(db.scalars(select(Booking).where(
        Booking.hotel_id == hotel.id, Booking.status.in_(PAID), Booking.check_in < end, Booking.check_out > start,
    )))

    result = []
    for room in rooms:
        cells = []
        for i in range(days):
            day = start + timedelta(days=i)
            stay = next((b for b in stays if b.room_id == room.id and b.check_in <= day < b.check_out), None)
            if stay:
                cells.append({"date": day, "state": "BOOKED", "booking_code": stay.booking_code, "booking_status": stay.status})
            elif room.status in (RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE):
                cells.append({"date": day, "state": "BLOCKED", "booking_code": None, "booking_status": None})
            else:
                cells.append({"date": day, "state": "FREE", "booking_code": None, "booking_status": None})
        result.append({"room_id": room.id, "room_number": room.room_number, "room_type_id": room.room_type_id, "days": cells})
    return result


def next_available(db: Session, room_type: RoomType, nights: int, from_date: date, search_days: int, options: int) -> list[dict]:
    """Scheduler: the first start dates where this room type is free for the whole stay."""
    if from_date < date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "from_date can't be in the past")
    found = []
    for i in range(search_days):
        check_in = from_date + timedelta(days=i)
        check_out = check_in + timedelta(days=nights)
        free = availability_service.count_free_rooms(db, room_type.id, check_in, check_out)
        if free:
            found.append({"check_in": check_in, "check_out": check_out, "available_rooms": free,
                          "total_price": pricing_service.stay_price(room_type, check_in, check_out)})
            if len(found) == options:
                break
    return found
