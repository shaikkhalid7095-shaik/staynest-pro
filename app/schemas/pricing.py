from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    room_type_id: int | None = None
    adjustment_percent: Decimal = Field(ge=-90, le=300, max_digits=5, decimal_places=2)
    start_date: date | None = None
    end_date: date | None = None
    days_of_week: str | None = Field(default=None, description='Monday=0 ... Sunday=6, e.g. "4,5"')

    @field_validator("days_of_week")
    @classmethod
    def check_days(cls, value):
        if value is None or value.strip() == "":
            return None
        parts = [p.strip() for p in value.split(",")]
        if not all(p.isdigit() and 0 <= int(p) <= 6 for p in parts):
            raise ValueError("days_of_week must be numbers 0-6 separated by commas")
        return ",".join(sorted(set(parts)))

    @model_validator(mode="after")
    def check_range(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date can't be before start_date")
        if not (self.start_date or self.end_date or self.days_of_week):
            raise ValueError("Give a date range, days_of_week, or both")
        return self


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    adjustment_percent: Decimal | None = Field(default=None, ge=-90, le=300, max_digits=5, decimal_places=2)
    is_active: bool | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    room_type_id: int | None
    name: str
    adjustment_percent: Decimal
    start_date: date | None
    end_date: date | None
    days_of_week: str | None
    is_active: bool
    created_at: datetime


class NightPrice(BaseModel):
    date: date
    weekday: str
    price: Decimal
    rules_applied: list[str]
