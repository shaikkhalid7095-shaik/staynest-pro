from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import Notification, User
from app.schemas.notification import NotificationOut, UnreadCount
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationOut])
def my_notifications(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return notification_service.list_for_user(db, user.id, unread_only, limit)


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"unread": notification_service.unread_count(db, user.id)}


@router.post("/read-all", response_model=UnreadCount)
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return {"unread": 0}


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(Notification, notification_id)
    # someone else's notification looks the same as a missing one
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    item.is_read = True
    db.commit()
    db.refresh(item)
    return item
