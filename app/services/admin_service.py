"""37 hotel moderation and 50 advanced platform administration."""

from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import (
    Booking, FraudFlag, Hotel, HotelStatus, Review, Role, RoleName, User,
)
from app.services import audit_service, auth_service, notification_service
from app.utils.time import utcnow


# ---------- 50. users ----------

def list_users(db: Session, role: str | None, is_active: bool | None, search: str | None, page: int, size: int) -> dict:
    query = select(User).join(Role, User.role_id == Role.id)
    if role:
        query = query.where(Role.name == role)
    if is_active is not None:
        query = query.where(User.is_active.is_(is_active))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(User.email.ilike(like), User.full_name.ilike(like), User.phone.ilike(like)))

    total = db.scalar(query.with_only_columns(func.count(User.id))) or 0
    users = list(db.scalars(query.order_by(User.id.desc()).offset((page - 1) * size).limit(size)))
    return {"total": total, "page": page, "size": size, "items": users}


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


def user_details(db: Session, user: User) -> dict:
    return {
        "bookings": db.scalar(select(func.count(Booking.id)).where(Booking.customer_id == user.id)) or 0,
        "hotels_owned": db.scalar(select(func.count(Hotel.id)).where(Hotel.owner_id == user.id)) or 0,
        "open_fraud_flags": db.scalar(select(func.count(FraudFlag.id)).where(
            FraudFlag.user_id == user.id, FraudFlag.status == "OPEN")) or 0,
        "last_login_at": user.last_login_at,
    }


def set_active(db: Session, target: User, active: bool, reason: str | None, admin: User, ip: str | None) -> User:
    if target.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't block your own account")
    if target.role.name == RoleName.ADMIN and not active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admins can't block other admins")

    target.is_active = active
    if not active:
        auth_service.revoke_all_tokens(db, target.id)  # log them out everywhere right now
    audit_service.log(db, admin.id, "USER_UNBLOCKED" if active else "USER_BLOCKED", "user", target.id, reason, ip)
    db.commit()
    db.refresh(target)
    return target


def force_logout(db: Session, target: User, admin: User, ip: str | None):
    auth_service.revoke_all_tokens(db, target.id)
    audit_service.log(db, admin.id, "FORCE_LOGOUT", "user", target.id, None, ip)
    db.commit()


def create_admin(db: Session, email: str, full_name: str, password: str, admin: User, ip: str | None) -> User:
    email = email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    role = db.scalar(select(Role).where(Role.name == RoleName.ADMIN.value))
    user = User(email=email, full_name=full_name, password_hash=hash_password(password), role=role, is_email_verified=True)
    db.add(user)
    db.flush()
    audit_service.log(db, admin.id, "ADMIN_CREATED", "user", user.id, email, ip)
    db.commit()
    db.refresh(user)
    return user


def system_health(db: Session) -> dict:
    try:
        db.execute(text("SELECT 1"))
        database = "connected"
    except Exception:  # noqa: BLE001 - we want to report any failure here
        database = "error"
    return {
        "database": database,
        "users": db.scalar(select(func.count(User.id))) or 0,
        "hotels": db.scalar(select(func.count(Hotel.id))) or 0,
        "bookings": db.scalar(select(func.count(Booking.id))) or 0,
        "stripe_configured": bool(settings.stripe_secret_key),
        "ai_configured": bool(settings.anthropic_api_key),
        "debug_mode": settings.debug,
        "server_time_utc": utcnow(),
    }


# ---------- 37. moderation ----------

def moderation_queue(db: Session) -> dict:
    pending = list(db.scalars(select(Hotel).where(Hotel.status == HotelStatus.PENDING.value).order_by(Hotel.created_at)))
    low_reviews = list(db.scalars(select(Review).where(
        Review.rating <= 2, Review.is_visible.is_(True), Review.created_at >= utcnow() - timedelta(days=30)
    ).order_by(Review.id.desc()).limit(20)))
    return {
        "pending_hotels": [{"id": h.id, "name": h.name, "city": h.city, "owner_email": h.owner.email,
                            "submitted_at": h.created_at} for h in pending],
        "low_rated_reviews": [{"id": r.id, "hotel_id": r.hotel_id, "rating": r.rating, "title": r.title,
                               "comment": r.comment, "created_at": r.created_at} for r in low_reviews],
        "open_fraud_flags": db.scalar(select(func.count(FraudFlag.id)).where(FraudFlag.status == "OPEN")) or 0,
    }


def change_hotel_status(db: Session, hotel: Hotel, new_status: str, reason: str | None, admin: User, ip: str | None) -> Hotel:
    if new_status == HotelStatus.SUSPENDED and not reason:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a reason for suspending")
    if new_status == HotelStatus.APPROVED and hotel.status != HotelStatus.SUSPENDED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a suspended hotel can be reinstated")

    hotel.status = new_status
    hotel.rejection_reason = reason if new_status == HotelStatus.SUSPENDED else None
    word = "suspended" if new_status == HotelStatus.SUSPENDED else "reinstated"
    notification_service.notify(
        db, hotel.owner_id, f"{hotel.name} was {word}",
        reason or f"{hotel.name} is visible to guests again.", type="MODERATION",
    )
    audit_service.log(db, admin.id, f"HOTEL_{word.upper()}", "hotel", hotel.id, reason, ip)
    db.commit()
    db.refresh(hotel)
    return hotel
