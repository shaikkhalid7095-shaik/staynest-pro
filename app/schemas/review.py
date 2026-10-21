from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=150)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    hotel_id: int
    customer_id: int
    rating: int
    title: str | None
    comment: str | None
    owner_reply: str | None
    replied_at: datetime | None
    is_visible: bool
    created_at: datetime


class ReviewReply(BaseModel):
    reply: str = Field(min_length=2, max_length=2000)


class ReviewVisibility(BaseModel):
    is_visible: bool


class HotelReviews(BaseModel):
    hotel_id: int
    avg_rating: float | None
    review_count: int
    reviews: list[ReviewOut]


class WishlistOut(BaseModel):
    hotel_id: int
    hotel_name: str
    city: str
    star_rating: int | None
    added_at: datetime