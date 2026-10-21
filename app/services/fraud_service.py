"""Simple rule-based fraud checks.

Each rule that matches adds points to a score. A booking that scores
anything is flagged for an admin to look at - we never block the guest
automatically, because a false alarm would lose a real customer.
"""

from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, FraudFlag, Payment, PaymentStatus, User
from app.services import audit_service, settings_service
from app.utils.time import utcnow

BIG_BOOKING_FOR_NEW_ACCOUNT = Decimal("20000")


def _count(db: Session, query) -> int:
    return db.scalar(query) or 0


def screen_booking(db: Session, booking: Booking) -> FraudFlag | None:
    now = utcnow()
    user_id = booking.customer_id
    score, reasons = 0, []

    limit = settings_service.get_int(db, "fraud_max_bookings_per_hour")
    last_hour = _count(db, select(func.count(Booking.id)).where(
        Booking.customer_id == user_id, Booking.created_at >= now - timedelta(hours=1)
    ))
    if last_hour > limit:
        score += 40
        reasons.append(f"{last_hour} bookings in the last hour")

    cancelled = _count(db, select(func.count(Booking.id)).where(
        Booking.customer_id == user_id,
        Booking.status == BookingStatus.CANCELLED.value,
        Booking.cancelled_at >= now - timedelta(days=30),
    ))
    if cancelled >= 3:
        score += 30
        reasons.append(f"{cancelled} cancellations in 30 days")

    failed_payments = _count(db, select(func.count(Payment.id)).join(Booking, Payment.booking_id == Booking.id).where(
        Booking.customer_id == user_id,
        Payment.status == PaymentStatus.FAILED.value,
        Payment.created_at >= now - timedelta(hours=24),
    ))
    if failed_payments >= 3:
        score += 30
        reasons.append(f"{failed_payments} failed payments in 24 hours")

    # much bigger than what this hotel usually gets
    hotel_avg = db.scalar(select(func.avg(Booking.total_amount)).where(
        Booking.hotel_id == booking.hotel_id, Booking.id != booking.id
    ))
    hotel_count = _count(db, select(func.count(Booking.id)).where(Booking.hotel_id == booking.hotel_id))
    if hotel_avg and hotel_count >= 4 and booking.total_amount > Decimal(hotel_avg) * 5:
        score += 30
        reasons.append("Amount is more than 5x this hotel's average booking")

    user = db.get(User, user_id)
    if user.created_at and user.created_at >= now - timedelta(days=1) and booking.total_amount >= BIG_BOOKING_FOR_NEW_ACCOUNT:
        score += 20
        reasons.append("Large booking from an account created today")

    if score == 0:
        return None

    flag = FraudFlag(booking_id=booking.id, user_id=user_id, score=min(score, 100), reasons="; ".join(reasons))
    db.add(flag)
    audit_service.log(db, None, "FRAUD_FLAGGED", "booking", booking.id, flag.reasons)
    db.commit()
    return flag


def list_flags(db: Session, flag_status: str | None, limit: int) -> list[FraudFlag]:
    query = select(FraudFlag)
    if flag_status:
        query = query.where(FraudFlag.status == flag_status)
    return list(db.scalars(query.order_by(FraudFlag.score.desc(), FraudFlag.id.desc()).limit(limit)))


def review_flag(db: Session, flag_id: int, new_status: str, note: str | None, admin: User, ip: str | None,
                block_user: bool) -> FraudFlag:
    flag = db.get(FraudFlag, flag_id)
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Flag not found")

    flag.status = new_status
    flag.review_note = note
    flag.reviewed_by_id = admin.id
    audit_service.log(db, admin.id, "FRAUD_REVIEWED", "fraud_flag", flag.id, f"{new_status}: {note or ''}", ip)

    if block_user and new_status == "CONFIRMED_FRAUD" and flag.user_id:
        user = db.get(User, flag.user_id)
        user.is_active = False
        audit_service.log(db, admin.id, "USER_BLOCKED", "user", user.id, "Confirmed fraud", ip)

    db.commit()
    db.refresh(flag)
    return flag
