from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas.notification import MessageCreate, MessageOut, UnreadCount
from app.services import booking_service, message_service

router = APIRouter(tags=["Messaging"])


@router.post("/bookings/{booking_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    booking_id: int, data: MessageCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # the same access rule as viewing the booking: guest, owner, staff or admin
    booking = booking_service.get_booking_for_user(db, booking_id, user)
    return MessageOut.from_row(message_service.send(db, booking, user, data.body))


@router.get("/bookings/{booking_id}/messages", response_model=list[MessageOut])
def read_thread(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = booking_service.get_booking_for_user(db, booking_id, user)
    return [MessageOut.from_row(m) for m in message_service.thread(db, booking, user)]


@router.get("/messages/unread-count", response_model=UnreadCount)
def unread_messages(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"unread": message_service.unread_count(db, user)}
