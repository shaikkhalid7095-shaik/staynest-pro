from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import RoleName, User
from app.schemas.room import (
    RoomCreate, RoomOut, RoomStatusUpdate, RoomTypeCreate, RoomTypeOut, RoomTypeUpdate, RoomUpdate,
)
from app.services import hotel_service, room_service

# rooms always live inside a hotel, so the hotel id is part of every URL
router = APIRouter(prefix="/hotels/{hotel_id}", tags=["Rooms & Room Types"])

owner_or_admin = require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)


@router.post("/room-types", response_model=RoomTypeOut, status_code=status.HTTP_201_CREATED)
def create_room_type(
    hotel_id: int, data: RoomTypeCreate, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return room_service.create_room_type(db, hotel, data)


@router.get("/room-types", response_model=list[RoomTypeOut])
def list_room_types(hotel_id: int, db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    return room_service.list_room_types(db, hotel, only_active=True)


@router.put("/room-types/{type_id}", response_model=RoomTypeOut)
def update_room_type(
    hotel_id: int,
    type_id: int,
    data: RoomTypeUpdate,
    user: User = Depends(owner_or_admin),
    db: Session = Depends(get_db),
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    room_type = room_service.get_room_type(db, hotel, type_id)
    return room_service.update_room_type(db, room_type, data)


@router.delete("/room-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room_type(
    hotel_id: int, type_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    room_type = room_service.get_room_type(db, hotel, type_id)
    room_service.delete_room_type(db, room_type)


@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    hotel_id: int, data: RoomCreate, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return room_service.create_room(db, hotel, data)


@router.get("/rooms", response_model=list[RoomOut])
def list_rooms(hotel_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    return room_service.list_rooms(db, hotel)


@router.put("/rooms/{room_id}", response_model=RoomOut)
def update_room(
    hotel_id: int,
    room_id: int,
    data: RoomUpdate,
    user: User = Depends(owner_or_admin),
    db: Session = Depends(get_db),
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    room = room_service.get_room(db, hotel, room_id)
    return room_service.update_room(db, hotel, room, data)


@router.patch("/rooms/{room_id}/status", response_model=RoomOut)
def change_room_status(
    hotel_id: int,
    room_id: int,
    data: RoomStatusUpdate,
    user: User = Depends(owner_or_admin),
    db: Session = Depends(get_db),
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    room = room_service.get_room(db, hotel, room_id)
    return room_service.set_room_status(db, room, data.status)


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(
    hotel_id: int, room_id: int, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)
):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    room = room_service.get_room(db, hotel, room_id)
    room_service.delete_room(db, room)
