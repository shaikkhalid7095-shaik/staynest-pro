from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import HotelStatus, RoleName, User
from app.schemas.hotel import (
    BranchCreate, BranchOut, HotelAmenitiesSet, HotelCreate, HotelOut, HotelUpdate, HotelVerify,
)
from app.services import hotel_service

router = APIRouter(prefix="/hotels", tags=["Hotels"])

owner_or_admin = require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)


@router.post("", response_model=HotelOut, status_code=status.HTTP_201_CREATED)
def register_hotel(
    data: HotelCreate,
    user: User = Depends(require_roles(RoleName.HOTEL_OWNER)),
    db: Session = Depends(get_db),
):
    return hotel_service.create_hotel(db, data, user)


@router.get("/my", response_model=list[HotelOut])
def my_hotels(user: User = Depends(require_roles(RoleName.HOTEL_OWNER)), db: Session = Depends(get_db)):
    return hotel_service.list_owner_hotels(db, user)


# admin routes come BEFORE "/{hotel_id}", otherwise "admin" is read as a hotel id
@router.get("/admin/by-status", response_model=list[HotelOut])
def hotels_by_status(
    hotel_status: HotelStatus = HotelStatus.PENDING,
    _: User = Depends(require_roles(RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    return hotel_service.list_by_status(db, hotel_status.value)


@router.patch("/{hotel_id}/verify", response_model=HotelOut)
def verify_hotel(
    hotel_id: int,
    data: HotelVerify,
    _: User = Depends(require_roles(RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    hotel = hotel_service.get_hotel_or_404(db, hotel_id)
    return hotel_service.verify_hotel(db, hotel, data)


@router.get("/{hotel_id}", response_model=HotelOut)
def get_hotel(hotel_id: int, db: Session = Depends(get_db)):
    return hotel_service.get_public_hotel(db, hotel_id)


@router.put("/{hotel_id}", response_model=HotelOut)
def update_hotel(
    hotel_id: int, data: HotelUpdate, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return hotel_service.update_hotel(db, hotel, data)


@router.delete("/{hotel_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_hotel(hotel_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    hotel_service.deactivate_hotel(db, hotel)


@router.put("/{hotel_id}/amenities", response_model=HotelOut)
def set_hotel_amenities(
    hotel_id: int,
    data: HotelAmenitiesSet,
    user: User = Depends(owner_or_admin),
    db: Session = Depends(get_db),
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return hotel_service.set_amenities(db, hotel, data.amenity_ids)


@router.post("/{hotel_id}/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
def add_branch(
    hotel_id: int, data: BranchCreate, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return hotel_service.add_branch(db, hotel, data)


@router.get("/{hotel_id}/branches", response_model=list[BranchOut])
def list_branches(hotel_id: int, db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    return [b for b in hotel.branches if b.is_active]


@router.delete("/{hotel_id}/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(
    hotel_id: int, branch_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    hotel_service.delete_branch(db, hotel, branch_id)
