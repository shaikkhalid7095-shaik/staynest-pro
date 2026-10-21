from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import RoleName, User
from app.schemas.booking import BookingOut
from app.schemas.service import CheckOutSummary
from app.services import booking_service, checkin_service, staff_service

router = APIRouter(tags=["Check-in & Check-out"])


def _front_desk_booking(db: Session, booking_id: int, user: User):
    # guests can't check themselves in - only the hotel side can
    if user.role.name == RoleName.CUSTOMER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Check-in is done by the hotel front desk")
    return booking_service.get_booking_for_user(db, booking_id, user)


@router.post("/bookings/{booking_id}/check-in", response_model=BookingOut)
def check_in(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return checkin_service.check_in(db, _front_desk_booking(db, booking_id, user))


@router.post("/bookings/{booking_id}/check-out", response_model=CheckOutSummary)
def check_out(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return checkin_service.check_out(db, _front_desk_booking(db, booking_id, user))


@router.get("/hotels/{hotel_id}/arrivals", response_model=list[BookingOut])
def arrivals(hotel_id: int, day: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    return checkin_service.arrivals(db, hotel, day or date.today())


@router.get("/hotels/{hotel_id}/departures", response_model=list[BookingOut])
def departures(hotel_id: int, day: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    return checkin_service.departures(db, hotel, day or date.today())


@router.get("/hotels/{hotel_id}/in-house", response_model=list[BookingOut])
def in_house(hotel_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    return checkin_service.in_house(db, hotel)
