from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Position = Literal["MANAGER", "RECEPTION", "HOUSEKEEPING", "KITCHEN", "MAINTENANCE"]
TaskType = Literal["CLEANING", "INSPECTION", "MAINTENANCE", "LAUNDRY"]
TaskStatus = Literal["PENDING", "IN_PROGRESS", "DONE"]
Priority = Literal["LOW", "NORMAL", "HIGH"]


class StaffCreate(BaseModel):
    # the owner creates the login for the staff member
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=64)
    phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$")
    position: Position


class StaffUpdate(BaseModel):
    position: Position | None = None
    is_active: bool | None = None


class StaffOut(BaseModel):
    id: int
    user_id: int
    hotel_id: int
    full_name: str
    email: str
    position: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_row(cls, staff):
        return cls(
            id=staff.id, user_id=staff.user_id, hotel_id=staff.hotel_id,
            full_name=staff.user.full_name, email=staff.user.email,
            position=staff.position, is_active=staff.is_active, created_at=staff.created_at,
        )


class TaskCreate(BaseModel):
    room_id: int
    task_type: TaskType
    priority: Priority = "NORMAL"
    notes: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    assigned_to_id: int | None = None  # a staff user id


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    priority: Priority | None = None
    notes: str | None = Field(default=None, max_length=255)
    assigned_to_id: int | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    room_id: int
    booking_id: int | None
    assigned_to_id: int | None
    task_type: str
    priority: str
    status: str
    notes: str | None
    due_date: date | None
    completed_at: datetime | None
    created_at: datetime
