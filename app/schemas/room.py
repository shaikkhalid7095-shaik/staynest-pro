from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RoomStatusValue = Literal["AVAILABLE", "OCCUPIED", "MAINTENANCE", "OUT_OF_SERVICE"]


class RoomTypeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = None
    base_price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    max_adults: int = Field(default=2, ge=1, le=10)
    max_children: int = Field(default=0, ge=0, le=10)
    bed_type: str | None = Field(default=None, max_length=30)
    size_sqft: int | None = Field(default=None, gt=0)


class RoomTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = None
    base_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    max_adults: int | None = Field(default=None, ge=1, le=10)
    max_children: int | None = Field(default=None, ge=0, le=10)
    bed_type: str | None = Field(default=None, max_length=30)
    size_sqft: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class RoomTypeOut(RoomTypeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    is_active: bool


class RoomCreate(BaseModel):
    room_type_id: int
    room_number: str = Field(min_length=1, max_length=10)
    floor: int | None = Field(default=None, ge=0, le=200)


class RoomUpdate(BaseModel):
    room_type_id: int | None = None
    room_number: str | None = Field(default=None, min_length=1, max_length=10)
    floor: int | None = Field(default=None, ge=0, le=200)
    is_active: bool | None = None


class RoomStatusUpdate(BaseModel):
    status: RoomStatusValue


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    room_type_id: int
    room_number: str
    floor: int | None
    status: str
    is_active: bool
