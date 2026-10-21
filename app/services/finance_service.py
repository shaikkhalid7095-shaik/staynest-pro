"""46. Financial management.

How money is split for a checked-out stay:
  guest paid (total_amount)  = room price - discount + GST
  platform commission        = commission % of (room price - discount)
  hotel payout (net)         = guest paid - commission
GST stays with the hotel, which files it. Extras (room service etc.)
are paid at the front desk, so they never pass through the platform.
"""

from datetime import date, datetime, time
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Booking, BookingStatus, Hotel, Payout, Refund, SubscriptionPayment, User,
)
from app.services import audit_service, notification_service, settings_service
from app.services.analytics_service import PAID
from app.utils.money import money
from app.utils.time import utcnow


def _rate(db: Session) -> Decimal:
    return settings_service.get_decimal(db, "platform_commission_percent") / 100


def hotel_summary(db: Session, hotel: Hotel, start: date, end: date) -> dict:
    stays = list(db.scalars(select(Booking).where(
        Booking.hotel_id == hotel.id,
        Booking.status == BookingStatus.CHECKED_OUT.value,
        Booking.check_out >= start, Booking.check_out <= end,
    )))
    rate = _rate(db)
    gross = sum((b.total_amount for b in stays), Decimal("0"))
    room_net = sum((b.subtotal - b.discount_amount for b in stays), Decimal("0"))
    tax = sum((b.tax_amount for b in stays), Decimal("0"))
    commission = money(room_net * rate)
    already_paid = db.scalar(select(func.coalesce(func.sum(Payout.net_amount), 0)).where(
        Payout.hotel_id == hotel.id, Payout.status == "PAID"
    ))
    return {
        "hotel_id": hotel.id, "hotel_name": hotel.name, "start": start, "end": end,
        "checked_out_stays": len(stays),
        "gross_amount": money(gross),
        "room_revenue": money(room_net),
        "tax_collected": money(tax),
        "commission_percent": money(rate * 100),
        "commission_amount": commission,
        "net_payable": money(gross - commission),
        "lifetime_paid_out": money(already_paid),
    }


def create_payout(db: Session, hotel: Hotel, start: date, end: date, admin: User, ip: str | None) -> Payout:
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "period_end must be on or after period_start")
    if end >= date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can only pay out periods that have finished")

    # never pay the same days twice
    overlap = db.scalar(select(Payout.id).where(
        Payout.hotel_id == hotel.id, Payout.period_start <= end, Payout.period_end >= start
    ))
    if overlap:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Payout #{overlap} already covers part of these dates")

    summary = hotel_summary(db, hotel, start, end)
    if summary["checked_out_stays"] == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No checked-out stays in this period")

    payout = Payout(
        hotel_id=hotel.id, period_start=start, period_end=end,
        bookings_count=summary["checked_out_stays"],
        gross_amount=summary["gross_amount"],
        commission_amount=summary["commission_amount"],
        net_amount=summary["net_payable"],
    )
    db.add(payout)
    db.flush()
    audit_service.log(db, admin.id, "PAYOUT_CREATED", "payout", payout.id, f"Rs {payout.net_amount} to hotel {hotel.id}", ip)
    db.commit()
    db.refresh(payout)
    return payout


def mark_paid(db: Session, payout_id: int, reference: str, admin: User, ip: str | None) -> Payout:
    payout = db.get(Payout, payout_id)
    if payout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payout not found")
    if payout.status == "PAID":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already paid")

    payout.status = "PAID"
    payout.reference = reference
    payout.paid_at = utcnow()
    notification_service.notify(
        db, payout.hotel.owner_id, "Payout sent",
        f"Rs {payout.net_amount} for {payout.period_start} to {payout.period_end} was sent (ref {reference}).",
        type="FINANCE",
    )
    audit_service.log(db, admin.id, "PAYOUT_PAID", "payout", payout.id, reference, ip)
    db.commit()
    db.refresh(payout)
    return payout


def list_payouts(db: Session, user: User, hotel_id: int | None) -> list[Payout]:
    query = select(Payout)
    if user.role.name != "ADMIN":
        query = query.join(Hotel, Payout.hotel_id == Hotel.id).where(Hotel.owner_id == user.id)
    if hotel_id:
        query = query.where(Payout.hotel_id == hotel_id)
    return list(db.scalars(query.order_by(Payout.id.desc())))


def platform_summary(db: Session, start: date, end: date) -> dict:
    start_dt, end_dt = datetime.combine(start, time.min), datetime.combine(end, time.max)
    paid = list(db.scalars(select(Booking).where(
        Booking.status.in_(PAID), Booking.check_in >= start, Booking.check_in <= end
    )))
    room_net = sum((b.subtotal - b.discount_amount for b in paid), Decimal("0"))
    refunds = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(
        Refund.status != "FAILED", Refund.created_at >= start_dt, Refund.created_at <= end_dt
    ))
    plans = db.scalar(select(func.coalesce(func.sum(SubscriptionPayment.amount), 0)).where(
        SubscriptionPayment.status == "SUCCEEDED",
        SubscriptionPayment.created_at >= start_dt, SubscriptionPayment.created_at <= end_dt,
    ))
    commission = money(room_net * _rate(db))
    pending = db.scalar(select(func.coalesce(func.sum(Payout.net_amount), 0)).where(Payout.status == "PENDING"))
    return {
        "start": start, "end": end,
        "bookings": len(paid),
        "gross_booking_value": money(sum((b.total_amount for b in paid), Decimal("0"))),
        "tax_collected": money(sum((b.tax_amount for b in paid), Decimal("0"))),
        "commission_earned": commission,
        "subscription_revenue": money(plans),
        "platform_income": money(commission + Decimal(plans)),
        "refunds_issued": money(refunds),
        "payouts_pending": money(pending),
    }
