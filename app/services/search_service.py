from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Amenity, Hotel, HotelImage, HotelStatus
from app.services import availability_service, pricing_service, review_service


def cover_images(db: Session, hotel_ids: list[int]) -> dict[int, str]:
    if not hotel_ids:
        return {}
    rows = db.scalars(
        select(HotelImage)
        .where(HotelImage.hotel_id.in_(hotel_ids))
        .order_by(HotelImage.is_cover.desc(), HotelImage.sort_order, HotelImage.id)
    )
    covers = {}
    for image in rows:
        covers.setdefault(image.hotel_id, image.image_url)  # first one wins
    return covers


def search_hotels(
    db: Session,
    city: str | None,
    check_in: date | None,
    check_out: date | None,
    adults: int,
    children: int,
    min_price: Decimal | None,
    max_price: Decimal | None,
    star_rating: int | None,
    property_type: str | None,
    amenity_ids: list[int],
    min_rating: float | None,
    sort: str,
    page: int,
    size: int,
) -> dict:
    if (check_in is None) != (check_out is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Send both check_in and check_out, or neither")
    if check_in:
        availability_service.validate_dates(check_in, check_out)

    # step 1: simple filters in SQL
    query = select(Hotel).where(Hotel.status == HotelStatus.APPROVED.value, Hotel.is_active.is_(True))
    if city:
        query = query.where(Hotel.city.ilike(f"%{city.strip()}%"))
    if star_rating:
        query = query.where(Hotel.star_rating >= star_rating)
    if property_type:
        query = query.where(Hotel.property_type == property_type.upper())
    for amenity_id in amenity_ids:
        # hotel must have EVERY selected amenity
        query = query.where(Hotel.amenities.any(Amenity.id == amenity_id))

    hotels = list(db.scalars(query))
    ids = [h.id for h in hotels]
    ratings = review_service.rating_stats(db, ids)
    covers = cover_images(db, ids)

    # step 2: filters that need room data, done in Python
    items = []
    for hotel in hotels:
        types = [
            t for t in hotel.room_types
            if t.is_active and t.max_adults >= adults and t.max_children >= children
        ]
        if check_in:
            types = [t for t in types if availability_service.count_free_rooms(db, t.id, check_in, check_out) > 0]
        if not types:
            continue

        price_date = check_in or date.today()
        starting_price = min(pricing_service.nightly_rate(t, price_date) for t in types)
        if min_price is not None and starting_price < min_price:
            continue
        if max_price is not None and starting_price > max_price:
            continue

        avg, count = ratings.get(hotel.id, (None, 0))
        if min_rating is not None and (avg is None or avg < min_rating):
            continue

        items.append({
            "id": hotel.id,
            "name": hotel.name,
            "property_type": hotel.property_type,
            "star_rating": hotel.star_rating,
            "city": hotel.city,
            "address_line": hotel.address_line,
            "starting_price": starting_price,
            "avg_rating": avg,
            "review_count": count,
            "amenities": [a.name for a in hotel.amenities],
            "cover_image": covers.get(hotel.id),
            "_created": hotel.created_at,
        })

    # step 3: sort
    if sort == "price_desc":
        items.sort(key=lambda i: i["starting_price"], reverse=True)
    elif sort == "rating":
        items.sort(key=lambda i: (i["avg_rating"] or 0, i["review_count"]), reverse=True)
    elif sort == "newest":
        items.sort(key=lambda i: i["_created"], reverse=True)
    else:
        items.sort(key=lambda i: i["starting_price"])

    # step 4: paginate
    total = len(items)
    start = (page - 1) * size
    page_items = items[start:start + size]
    for item in page_items:
        item.pop("_created")

    return {"items": page_items, "total": total, "page": page, "size": size}