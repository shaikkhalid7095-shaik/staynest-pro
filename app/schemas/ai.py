from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecommendedHotel(BaseModel):
    hotel_id: int
    name: str
    city: str
    star_rating: int | None
    starting_price: Decimal
    avg_rating: float | None
    score: float
    reasons: list[str]


class TravelRequest(BaseModel):
    city: str = Field(min_length=2, max_length=100)
    days: int = Field(default=3, ge=1, le=14)
    budget_per_night: Decimal | None = Field(default=None, gt=0)
    interests: str | None = Field(default=None, max_length=200, description="e.g. beaches, food, temples")
    question: str | None = Field(default=None, max_length=500)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class AIAnswer(BaseModel):
    answer: str
    source: Literal["claude", "rules"]
    hotels: list[RecommendedHotel] = []


class ChatHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel: str
    role: str
    content: str
    created_at: datetime
