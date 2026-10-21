from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    message: str
    type: str
    reference: str | None
    is_read: bool
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    sender_id: int
    sender_name: str
    body: str
    is_read: bool
    created_at: datetime

    @classmethod
    def from_row(cls, msg):
        return cls(
            id=msg.id, booking_id=msg.booking_id, sender_id=msg.sender_id,
            sender_name=msg.sender.full_name, body=msg.body,
            is_read=msg.is_read, created_at=msg.created_at,
        )
