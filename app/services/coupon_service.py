from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Coupon, Hotel, RoleName, User
from app.schemas.coupon import CouponCreate, CouponUpdate
from app.services import hotel_service


def create_coupon(db: Session, data: CouponCreate, user: User) -> Coupon:
    if user.role.name == RoleName.HOTEL_OWNER:
        if data.hotel_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hotel owners must give a hotel_id")
        hotel_service.get_manageable_hotel(db, data.hotel_id, user)
    elif data.hotel_id is not None:
        hotel_service.get_hotel_or_404(db, data.hotel_id)

    if db.scalar(select(Coupon).where(Coupon.code == data.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Coupon code already exists")

    coupon = Coupon(**data.model_dump(), created_by_id=user.id)
    db.add(coupon)
    db.commit()
    db.refresh(coupon)
    return coupon


def list_coupons(db: Session, user: User) -> list[Coupon]:
    query = select(Coupon)
    if user.role.name == RoleName.HOTEL_OWNER:
        own_hotels = select(Hotel.id).where(Hotel.owner_id == user.id)
        query = query.where(Coupon.hotel_id.in_(own_hotels))
    return list(db.scalars(query.order_by(Coupon.id.desc())))


def get_manageable_coupon(db: Session, coupon_id: int, user: User) -> Coupon:
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coupon not found")
    if user.role.name == RoleName.HOTEL_OWNER:
        if coupon.hotel_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform coupons are managed by admin")
        hotel_service.get_manageable_hotel(db, coupon.hotel_id, user)
    return coupon


def update_coupon(db: Session, coupon: Coupon, data: CouponUpdate) -> Coupon:
    changes = data.model_dump(exclude_unset=True)
    if "valid_until" in changes and changes["valid_until"] <= coupon.valid_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "valid_until must be after valid_from")
    for field, value in changes.items():
        setattr(coupon, field, value)
    db.commit()
    db.refresh(coupon)
    return coupon