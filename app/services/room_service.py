from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Hotel, Room, RoomType
from app.schemas.room import RoomCreate, RoomTypeCreate, RoomTypeUpdate, RoomUpdate


# ---------- room types ----------

def _check_type_name_free(db: Session, hotel_id: int, name: str, skip_id: int | None = None):
    query = select(RoomType).where(RoomType.hotel_id == hotel_id, RoomType.name == name)
    existing = db.scalar(query)
    if existing and existing.id != skip_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Room type '{name}' already exists in this hotel")


def get_room_type(db: Session, hotel: Hotel, type_id: int) -> RoomType:
    room_type = db.get(RoomType, type_id)
    # a room type id from another hotel counts as "not found" here
    if room_type is None or room_type.hotel_id != hotel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room type not found")
    return room_type


def list_room_types(db: Session, hotel: Hotel, only_active: bool = False) -> list[RoomType]:
    query = select(RoomType).where(RoomType.hotel_id == hotel.id)
    if only_active:
        query = query.where(RoomType.is_active.is_(True))
    return list(db.scalars(query.order_by(RoomType.base_price)))


def create_room_type(db: Session, hotel: Hotel, data: RoomTypeCreate) -> RoomType:
    _check_type_name_free(db, hotel.id, data.name)
    room_type = RoomType(**data.model_dump(), hotel_id=hotel.id)
    db.add(room_type)
    db.commit()
    db.refresh(room_type)
    return room_type


def update_room_type(db: Session, room_type: RoomType, data: RoomTypeUpdate) -> RoomType:
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _check_type_name_free(db, room_type.hotel_id, changes["name"], skip_id=room_type.id)
    for field, value in changes.items():
        setattr(room_type, field, value)
    db.commit()
    db.refresh(room_type)
    return room_type


def delete_room_type(db: Session, room_type: RoomType):
    room_count = db.scalar(select(func.count(Room.id)).where(Room.room_type_id == room_type.id))
    if room_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{room_count} room(s) still use this type. Move or delete them first",
        )
    db.delete(room_type)
    db.commit()


# ---------- rooms ----------

def _check_room_number_free(db: Session, hotel_id: int, number: str, skip_id: int | None = None):
    existing = db.scalar(select(Room).where(Room.hotel_id == hotel_id, Room.room_number == number))
    if existing and existing.id != skip_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Room {number} already exists in this hotel")


def get_room(db: Session, hotel: Hotel, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None or room.hotel_id != hotel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")
    return room


def list_rooms(db: Session, hotel: Hotel) -> list[Room]:
    return list(db.scalars(select(Room).where(Room.hotel_id == hotel.id).order_by(Room.room_number)))


def create_room(db: Session, hotel: Hotel, data: RoomCreate) -> Room:
    get_room_type(db, hotel, data.room_type_id)  # makes sure the type belongs to this hotel
    _check_room_number_free(db, hotel.id, data.room_number)

    room = Room(**data.model_dump(), hotel_id=hotel.id)
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


def update_room(db: Session, hotel: Hotel, room: Room, data: RoomUpdate) -> Room:
    changes = data.model_dump(exclude_unset=True)
    if "room_type_id" in changes:
        get_room_type(db, hotel, changes["room_type_id"])
    if "room_number" in changes:
        _check_room_number_free(db, hotel.id, changes["room_number"], skip_id=room.id)

    for field, value in changes.items():
        setattr(room, field, value)
    db.commit()
    db.refresh(room)
    return room


def set_room_status(db: Session, room: Room, new_status: str) -> Room:
    room.status = new_status
    db.commit()
    db.refresh(room)
    return room


def delete_room(db: Session, room: Room):
    from app.models import Booking  # rooms with bookings can't be deleted

    if db.scalar(select(func.count(Booking.id)).where(Booking.room_id == room.id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This room has bookings. Set its status to OUT_OF_SERVICE instead"
        )
    db.delete(room)
    db.commit()
