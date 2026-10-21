from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Notification


def notify(db: Session, user_id: int, title: str, message: str, type: str = "GENERAL", reference: str | None = None):
    # only adds the row - the caller commits together with its own changes,
    # so a notification is never saved for something that failed
    db.add(Notification(user_id=user_id, title=title, message=message, type=type, reference=reference))


def list_for_user(db: Session, user_id: int, unread_only: bool, limit: int) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    return list(db.scalars(query.order_by(Notification.id.desc()).limit(limit)))


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
    ) or 0
