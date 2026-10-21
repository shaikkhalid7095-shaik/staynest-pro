from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Amenity, Hotel, HotelBranch, HotelStatus, RoleName, User
from app.schemas.hotel import BranchCreate, HotelCreate, HotelUpdate, HotelVerify


def get_hotel_or_404(db: Session, hotel_id: int) -> Hotel:
    hotel = db.get(Hotel, hotel_id)
    if hotel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hotel not found")
    return hotel


def get_public_hotel(db: Session, hotel_id: int) -> Hotel:
    hotel = get_hotel_or_404(db, hotel_id)
    # customers should never see pending or rejected hotels
    if hotel.status != HotelStatus.APPROVED or not hotel.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hotel not found")
    return hotel


def get_manageable_hotel(db: Session, hotel_id: int, user: User) -> Hotel:
    # owner of this hotel, or an admin
    hotel = get_hotel_or_404(db, hotel_id)
    if user.role.name != RoleName.ADMIN and hotel.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your hotel")
    return hotel


def create_hotel(db: Session, data: HotelCreate, owner: User) -> Hotel:
    from app.services import subscription_service  # day 3: plan limits

    limit, plan_name = subscription_service.hotel_limit(db, owner.id)
    if subscription_service.hotels_used(db, owner.id) >= limit:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Your {plan_name} plan allows {limit} hotel(s). Upgrade your plan at POST /subscriptions",
        )

    hotel = Hotel(**data.model_dump(), owner_id=owner.id, status=HotelStatus.PENDING.value)
    db.add(hotel)
    db.commit()
    db.refresh(hotel)
    return hotel


def list_owner_hotels(db: Session, owner: User) -> list[Hotel]:
    return list(db.scalars(select(Hotel).where(Hotel.owner_id == owner.id).order_by(Hotel.id)))


def update_hotel(db: Session, hotel: Hotel, data: HotelUpdate) -> Hotel:
    # exclude_unset: only the fields the client actually sent
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(hotel, field, value)
    db.commit()
    db.refresh(hotel)
    return hotel


def deactivate_hotel(db: Session, hotel: Hotel):
    # soft delete - old bookings and reviews still point to this hotel
    hotel.is_active = False
    db.commit()


def list_by_status(db: Session, hotel_status: str) -> list[Hotel]:
    return list(db.scalars(select(Hotel).where(Hotel.status == hotel_status).order_by(Hotel.id)))


def verify_hotel(db: Session, hotel: Hotel, data: HotelVerify) -> Hotel:
    if data.status in ("REJECTED", "SUSPENDED") and not data.reason:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please give a reason")

    hotel.status = data.status
    hotel.rejection_reason = data.reason if data.status != "APPROVED" else None
    db.commit()
    db.refresh(hotel)
    return hotel


def set_amenities(db: Session, hotel: Hotel, amenity_ids: list[int]) -> Hotel:
    ids = set(amenity_ids)
    amenities = list(db.scalars(select(Amenity).where(Amenity.id.in_(ids)))) if ids else []
    if len(amenities) != len(ids):
        found = {a.id for a in amenities}
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown amenity ids: {sorted(ids - found)}")

    hotel.amenities = amenities
    db.commit()
    db.refresh(hotel)
    return hotel


def add_branch(db: Session, hotel: Hotel, data: BranchCreate) -> HotelBranch:
    branch = HotelBranch(**data.model_dump(), hotel_id=hotel.id)
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


def delete_branch(db: Session, hotel: Hotel, branch_id: int):
    branch = db.get(HotelBranch, branch_id)
    if branch is None or branch.hotel_id != hotel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
    db.delete(branch)
    db.commit()
