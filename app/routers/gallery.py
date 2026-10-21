from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import HotelImage, RoleName, User
from app.schemas.hotel import HotelOut
from app.schemas.room import RoomTypeOut
from app.schemas.search import HotelDetails, HotelImageCreate, HotelImageOut
from app.services import hotel_service, review_service, room_service

router = APIRouter(prefix="/hotels/{hotel_id}", tags=["Hotel Details & Gallery"])

owner_or_admin = require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)


def _images(db: Session, hotel_id: int) -> list[HotelImage]:
    query = (
        select(HotelImage)
        .where(HotelImage.hotel_id == hotel_id)
        .order_by(HotelImage.is_cover.desc(), HotelImage.sort_order, HotelImage.id)
    )
    return list(db.scalars(query))


@router.get("/details", response_model=HotelDetails)
def hotel_details(hotel_id: int, db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    avg, count = review_service.rating_stats(db, [hotel.id]).get(hotel.id, (None, 0))

    return HotelDetails(
        **HotelOut.model_validate(hotel).model_dump(),
        images=[HotelImageOut.model_validate(i) for i in _images(db, hotel.id)],
        room_types=[RoomTypeOut.model_validate(t) for t in room_service.list_room_types(db, hotel, only_active=True)],
        avg_rating=avg,
        review_count=count,
    )


@router.get("/images", response_model=list[HotelImageOut])
def list_images(hotel_id: int, db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    return _images(db, hotel.id)


@router.post("/images", response_model=HotelImageOut, status_code=status.HTTP_201_CREATED)
def add_image(
    hotel_id: int, data: HotelImageCreate, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    if data.is_cover:
        # only one cover photo per hotel
        db.execute(update(HotelImage).where(HotelImage.hotel_id == hotel.id).values(is_cover=False))

    image = HotelImage(**data.model_dump(), hotel_id=hotel.id)
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    hotel_id: int, image_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    image = db.get(HotelImage, image_id)
    if image is None or image.hotel_id != hotel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    db.delete(image)
    db.commit()