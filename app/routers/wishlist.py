from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import RoleName, User, WishlistItem
from app.schemas.review import WishlistOut
from app.services import hotel_service

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])

customer_only = require_roles(RoleName.CUSTOMER)


def _to_out(item: WishlistItem) -> WishlistOut:
    return WishlistOut(
        hotel_id=item.hotel_id,
        hotel_name=item.hotel.name,
        city=item.hotel.city,
        star_rating=item.hotel.star_rating,
        added_at=item.created_at,
    )


@router.get("", response_model=list[WishlistOut])
def my_wishlist(user: User = Depends(customer_only), db: Session = Depends(get_db)):
    items = db.scalars(
        select(WishlistItem).where(WishlistItem.customer_id == user.id).order_by(WishlistItem.id.desc())
    )
    return [_to_out(i) for i in items]


@router.post("/{hotel_id}", response_model=WishlistOut, status_code=status.HTTP_201_CREATED)
def add_to_wishlist(hotel_id: int, user: User = Depends(customer_only), db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    existing = db.scalar(
        select(WishlistItem).where(WishlistItem.customer_id == user.id, WishlistItem.hotel_id == hotel.id)
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Hotel is already in your wishlist")

    item = WishlistItem(customer_id=user.id, hotel_id=hotel.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/{hotel_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_wishlist(hotel_id: int, user: User = Depends(customer_only), db: Session = Depends(get_db)):
    item = db.scalar(
        select(WishlistItem).where(WishlistItem.customer_id == user.id, WishlistItem.hotel_id == hotel_id)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hotel is not in your wishlist")
    db.delete(item)
    db.commit()