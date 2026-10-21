from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Booking, Hotel, HotelStaff, Message, RoleName, User
from app.services import notification_service


def send(db: Session, booking: Booking, sender: User, body: str) -> Message:
    msg = Message(booking_id=booking.id, sender_id=sender.id, body=body.strip())
    db.add(msg)

    # tell the other side
    preview = body.strip()[:80]
    if sender.id == booking.customer_id:
        notification_service.notify(
            db, booking.hotel.owner_id, f"Message from guest ({booking.booking_code})", preview,
            type="MESSAGE", reference=f"booking:{booking.id}",
        )
    else:
        notification_service.notify(
            db, booking.customer_id, f"Message from {booking.hotel.name}", preview,
            type="MESSAGE", reference=f"booking:{booking.id}",
        )
    db.commit()
    db.refresh(msg)
    return msg


def thread(db: Session, booking: Booking, reader: User) -> list[Message]:
    # opening the chat marks the other side's messages as read
    db.execute(
        update(Message)
        .where(Message.booking_id == booking.id, Message.sender_id != reader.id, Message.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return list(db.scalars(select(Message).where(Message.booking_id == booking.id).order_by(Message.id)))


def _my_booking_ids(db: Session, user: User):
    role = user.role.name
    if role == RoleName.CUSTOMER:
        return select(Booking.id).where(Booking.customer_id == user.id)
    if role == RoleName.HOTEL_OWNER:
        return select(Booking.id).join(Hotel, Booking.hotel_id == Hotel.id).where(Hotel.owner_id == user.id)
    if role == RoleName.HOTEL_STAFF:
        hotel_ids = select(HotelStaff.hotel_id).where(HotelStaff.user_id == user.id, HotelStaff.is_active.is_(True))
        return select(Booking.id).where(Booking.hotel_id.in_(hotel_ids))
    return select(Booking.id)  # admin


def unread_count(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count(Message.id)).where(
            Message.booking_id.in_(_my_booking_ids(db, user)),
            Message.sender_id != user.id,
            Message.is_read.is_(False),
        )
    ) or 0
