from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Hotel, HotelStaff, Role, RoleName, User
from app.schemas.staff import StaffCreate, StaffUpdate
from app.services import hotel_service


def staff_row(db: Session, user: User) -> HotelStaff | None:
    if user.role.name != RoleName.HOTEL_STAFF:
        return None
    return db.scalar(select(HotelStaff).where(HotelStaff.user_id == user.id, HotelStaff.is_active.is_(True)))


def works_at(db: Session, user: User, hotel_id: int) -> bool:
    row = staff_row(db, user)
    return row is not None and row.hotel_id == hotel_id


def get_operable_hotel(db: Session, hotel_id: int, user: User) -> Hotel:
    """Hotel that this user can run day-to-day: admin, the owner, or its own staff."""
    hotel = hotel_service.get_hotel_or_404(db, hotel_id)
    role = user.role.name
    if role == RoleName.ADMIN:
        return hotel
    if role == RoleName.HOTEL_OWNER and hotel.owner_id == user.id:
        return hotel
    if role == RoleName.HOTEL_STAFF and works_at(db, user, hotel.id):
        return hotel
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't work at this hotel")


def add_staff(db: Session, hotel: Hotel, data: StaffCreate) -> HotelStaff:
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    if data.phone and db.scalar(select(User).where(User.phone == data.phone)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone number is already registered")

    role = db.scalar(select(Role).where(Role.name == RoleName.HOTEL_STAFF.value))
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role=role,
        is_email_verified=True,  # the owner created it, so we trust the email
    )
    staff = HotelStaff(user=user, hotel_id=hotel.id, position=data.position)
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def list_staff(db: Session, hotel: Hotel) -> list[HotelStaff]:
    return list(db.scalars(select(HotelStaff).where(HotelStaff.hotel_id == hotel.id).order_by(HotelStaff.id)))


def get_staff(db: Session, hotel: Hotel, staff_id: int) -> HotelStaff:
    staff = db.get(HotelStaff, staff_id)
    if staff is None or staff.hotel_id != hotel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
    return staff


def update_staff(db: Session, staff: HotelStaff, data: StaffUpdate) -> HotelStaff:
    changes = data.model_dump(exclude_unset=True)
    if "position" in changes:
        staff.position = changes["position"]
    if "is_active" in changes:
        staff.is_active = changes["is_active"]
        # a removed staff member must not be able to log in any more
        staff.user.is_active = changes["is_active"]
    db.commit()
    db.refresh(staff)
    return staff
