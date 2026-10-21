from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import RoleName, User
from app.schemas.coupon import (
    CouponCreate, CouponOut, CouponUpdate, CouponValidateRequest, CouponValidateResponse,
)
from app.services import coupon_service, pricing_service
from app.utils.money import money

router = APIRouter(prefix="/coupons", tags=["Coupons"])

admin_or_owner = require_roles(RoleName.ADMIN, RoleName.HOTEL_OWNER)


@router.post("", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
def create_coupon(data: CouponCreate, user: User = Depends(admin_or_owner), db: Session = Depends(get_db)):
    return coupon_service.create_coupon(db, data, user)


@router.get("", response_model=list[CouponOut])
def list_coupons(user: User = Depends(admin_or_owner), db: Session = Depends(get_db)):
    return coupon_service.list_coupons(db, user)


@router.post("/validate", response_model=CouponValidateResponse)
def validate_coupon(
    data: CouponValidateRequest,
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    amount = money(data.amount)
    coupon, discount = pricing_service.coupon_discount(db, data.code, data.hotel_id, user.id, amount)
    return CouponValidateResponse(code=coupon.code, discount_amount=discount, amount_after_discount=amount - discount)


@router.patch("/{coupon_id}", response_model=CouponOut)
def update_coupon(
    coupon_id: int, data: CouponUpdate, user: User = Depends(admin_or_owner), db: Session = Depends(get_db)
):
    coupon = coupon_service.get_manageable_coupon(db, coupon_id, user)
    return coupon_service.update_coupon(db, coupon, data)


@router.delete("/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_coupon(coupon_id: int, user: User = Depends(admin_or_owner), db: Session = Depends(get_db)):
    # soft delete: old bookings still point to this coupon
    coupon = coupon_service.get_manageable_coupon(db, coupon_id, user)
    coupon.is_active = False
    db.commit()