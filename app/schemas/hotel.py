from datetime import datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

PropertyType = Literal["HOTEL", "RESORT", "HOMESTAY", "VILLA", "HOSTEL"]


class AmenityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category: str = Field(default="GENERAL", max_length=30)


class AmenityOut(AmenityCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class HotelAmenitiesSet(BaseModel):
    amenity_ids: list[int]


class HotelCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    property_type: PropertyType = "HOTEL"
    star_rating: int | None = Field(default=None, ge=1, le=5)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")
    address_line: str = Field(min_length=3, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    state: str | None = None
    country: str = "India"
    postal_code: str | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    check_in_time: time = time(14, 0)
    check_out_time: time = time(11, 0)


class HotelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    property_type: PropertyType | None = None
    star_rating: int | None = Field(default=None, ge=1, le=5)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    check_in_time: time | None = None
    check_out_time: time | None = None


class HotelOut(HotelCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    status: str
    rejection_reason: str | None
    is_active: bool
    created_at: datetime
    amenities: list[AmenityOut] = []


class HotelVerify(BaseModel):
    status: Literal["APPROVED", "REJECTED", "SUSPENDED"]
    reason: str | None = Field(default=None, max_length=255)


class BranchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    address_line: str = Field(min_length=3, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    state: str | None = None
    postal_code: str | None = None
    phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")


class BranchOut(BranchCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    is_active: bool
