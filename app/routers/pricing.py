from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import PricingRule, RoleName, User
from app.schemas.pricing import NightPrice, RuleCreate, RuleOut, RuleUpdate
from app.services import hotel_service, pricing_service, room_service

router = APIRouter(prefix="/hotels/{hotel_id}", tags=["Dynamic Pricing"])

owner_or_admin = require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)


def _get_rule(db: Session, hotel_id: int, rule_id: int) -> PricingRule:
    rule = db.get(PricingRule, rule_id)
    if rule is None or rule.hotel_id != hotel_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pricing rule not found")
    return rule


@router.post("/pricing-rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(hotel_id: int, data: RuleCreate, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    if data.room_type_id is not None:
        room_service.get_room_type(db, hotel, data.room_type_id)  # must belong to this hotel
    rule = PricingRule(**data.model_dump(), hotel_id=hotel.id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/pricing-rules", response_model=list[RuleOut])
def list_rules(hotel_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return list(db.scalars(select(PricingRule).where(PricingRule.hotel_id == hotel.id).order_by(PricingRule.id)))


@router.patch("/pricing-rules/{rule_id}", response_model=RuleOut)
def update_rule(
    hotel_id: int, rule_id: int, data: RuleUpdate,
    user: User = Depends(owner_or_admin), db: Session = Depends(get_db),
):
    hotel_service.get_manageable_hotel(db, hotel_id, user)
    rule = _get_rule(db, hotel_id, rule_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/pricing-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(hotel_id: int, rule_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel_service.get_manageable_hotel(db, hotel_id, user)
    db.delete(_get_rule(db, hotel_id, rule_id))
    db.commit()


@router.get("/price-calendar", response_model=list[NightPrice])
def price_calendar(
    hotel_id: int,
    room_type_id: int,
    start: date | None = None,
    days: int = Query(14, ge=1, le=60),
    db: Session = Depends(get_db),
):
    # public: lets a guest see which nights are cheaper
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    room_type = room_service.get_room_type(db, hotel, room_type_id)
    return pricing_service.price_calendar(room_type, start or date.today(), days)
