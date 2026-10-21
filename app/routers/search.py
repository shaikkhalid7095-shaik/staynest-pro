from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.search import HotelSearchPage, RoomTypeAvailability
from app.services import availability_service, hotel_service, search_service

router = APIRouter(tags=["Search & Availability"])


@router.get("/search/hotels", response_model=HotelSearchPage)
def search_hotels(
    city: str | None = None,
    check_in: date | None = None,
    check_out: date | None = None,
    adults: int = Query(1, ge=1, le=10),
    children: int = Query(0, ge=0, le=10),
    min_price: Decimal | None = Query(None, ge=0),
    max_price: Decimal | None = Query(None, ge=0),
    star_rating: int | None = Query(None, ge=1, le=5, description="Minimum stars"),
    property_type: str | None = Query(None, description="HOTEL, RESORT, HOMESTAY, VILLA, HOSTEL"),
    amenity_ids: list[int] = Query(default=[], description="Hotel must have all of these"),
    min_rating: float | None = Query(None, ge=1, le=5),
    sort: Literal["price_asc", "price_desc", "rating", "newest"] = "price_asc",
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return search_service.search_hotels(
        db, city, check_in, check_out, adults, children, min_price, max_price,
        star_rating, property_type, amenity_ids, min_rating, sort, page, size,
    )


@router.get("/hotels/{hotel_id}/availability", response_model=list[RoomTypeAvailability])
def hotel_availability(
    hotel_id: int,
    check_in: date,
    check_out: date,
    adults: int = Query(1, ge=1, le=10),
    children: int = Query(0, ge=0, le=10),
    db: Session = Depends(get_db),
):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    return availability_service.hotel_availability(db, hotel, check_in, check_out, adults, children)