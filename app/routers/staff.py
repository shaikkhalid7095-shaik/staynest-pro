from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import RoleName, User
from app.schemas.hotel import HotelOut
from app.schemas.staff import StaffCreate, StaffOut, StaffUpdate
from app.services import hotel_service, staff_service

router = APIRouter(tags=["Staff"])

owner_or_admin = require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)


@router.post("/hotels/{hotel_id}/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
def add_staff(hotel_id: int, data: StaffCreate, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return StaffOut.from_row(staff_service.add_staff(db, hotel, data))


@router.get("/hotels/{hotel_id}/staff", response_model=list[StaffOut])
def list_staff(hotel_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return [StaffOut.from_row(s) for s in staff_service.list_staff(db, hotel)]


@router.patch("/hotels/{hotel_id}/staff/{staff_id}", response_model=StaffOut)
def update_staff(
    hotel_id: int, staff_id: int, data: StaffUpdate,
    user: User = Depends(owner_or_admin), db: Session = Depends(get_db),
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    staff = staff_service.get_staff(db, hotel, staff_id)
    return StaffOut.from_row(staff_service.update_staff(db, staff, data))


@router.get("/staff/me", response_model=HotelOut)
def my_workplace(user: User = Depends(require_roles(RoleName.HOTEL_STAFF)), db: Session = Depends(get_db)):
    # lets a staff member find out which hotel id to use in the other APIs
    row = staff_service.staff_row(db, user)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not assigned to a hotel")
    return hotel_service.get_hotel_or_404(db, row.hotel_id)
