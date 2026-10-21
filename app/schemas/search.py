from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.hotel import HotelOut
from app.schemas.room import RoomTypeOut


class RoomTypeAvailability(BaseModel):
    room_type_id: int
    name: str
    max_adults: int
    max_children: int
    price_per_night: Decimal
    nights: int
    estimated_total: Decimal  # before coupon and tax
    available_rooms: int


class HotelSearchItem(BaseModel):
    id: int
    name: str
    property_type: str
    star_rating: int | None
    city: str
    address_line: str
    starting_price: Decimal
    avg_rating: float | None
    review_count: int
    amenities: list[str]
    cover_image: str | None


class HotelSearchPage(BaseModel):
    items: list[HotelSearchItem]
    total: int
    page: int
    size: int


class HotelImageCreate(BaseModel):
    image_url: str = Field(max_length=500, pattern=r"^https?://")
    caption: str | None = Field(default=None, max_length=150)
    is_cover: bool = False
    sort_order: int = Field(default=0, ge=0, le=999)


class HotelImageOut(HotelImageCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int


class HotelDetails(HotelOut):
    images: list[HotelImageOut]
    room_types: list[RoomTypeOut]
    avg_rating: float | None
    review_count: int