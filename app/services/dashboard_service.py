"""34-36. One call that gives each role the numbers for its home screen."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Booking, BookingStatus, FraudFlag, Hotel, HotelStatus, HotelSubscription, HousekeepingTask, LoginAttempt,
    Payout, Review, Role, Room, ServiceOrder, User, WishlistItem,
)
from app.services import (
    analytics_service, booking_service, finance_service, loyalty_service, message_service,
    notification_service, review_service, subscription_service,
)
from app.utils.money import money
from app.utils.time import utcnow


def _count(db: Session, query) -> int:
    return db.scalar(query) or 0


def _short(b: Booking) -> dict:
    return {"booking_id": b.id, "booking_code": b.booking_code, "hotel": b.hotel.name, "guest": b.customer.full_name,
            "check_in": b.check_in, "check_out": b.check_out, "status": b.status, "total_amount": b.total_amount}


def owner(db: Session, user: User) -> dict:
    today = date.today()
    hotels = list(db.scalars(select(Hotel).where(Hotel.owner_id == user.id).order_by(Hotel.id)))
    ids = [h.id for h in hotels] or [-1]
    month_start = today.replace(day=1)

    in_house = _count(db, select(func.count(Booking.id)).where(
        Booking.hotel_id.in_(ids), Booking.status == BookingStatus.CHECKED_IN.value))
    total_rooms = _count(db, select(func.count(Room.id)).where(Room.hotel_id.in_(ids), Room.is_active.is_(True)))
    arrivals = list(db.scalars(select(Booking).where(
        Booking.hotel_id.in_(ids), Booking.status == BookingStatus.CONFIRMED.value, Booking.check_in >= today,
    ).order_by(Booking.check_in).limit(5)))
    ratings = review_service.rating_stats(db, ids)
    limit, plan = subscription_service.hotel_limit(db, user.id)

    return {
        "plan": plan, "hotel_limit": limit,
        "hotels": [{"id": h.id, "name": h.name, "city": h.city, "status": h.status,
                    "avg_rating": ratings.get(h.id, (None, 0))[0]} for h in hotels],
        "arrivals_today": _count(db, select(func.count(Booking.id)).where(
            Booking.hotel_id.in_(ids), Booking.check_in == today, Booking.status == BookingStatus.CONFIRMED.value)),
        "departures_today": _count(db, select(func.count(Booking.id)).where(
            Booking.hotel_id.in_(ids), Booking.check_out == today, Booking.status == BookingStatus.CHECKED_IN.value)),
        "in_house_guests": in_house,
        "occupancy_today_percent": round(in_house / total_rooms * 100, 1) if total_rooms else 0.0,
        "revenue_this_month": analytics_service.revenue(db, ids, month_start, today, "month")["total_revenue"],
        "open_service_orders": _count(db, select(func.count(ServiceOrder.id)).join(Booking, ServiceOrder.booking_id == Booking.id)
                                      .where(Booking.hotel_id.in_(ids), ServiceOrder.status.in_(["REQUESTED", "IN_PROGRESS"]))),
        "open_housekeeping_tasks": _count(db, select(func.count(HousekeepingTask.id)).where(
            HousekeepingTask.hotel_id.in_(ids), HousekeepingTask.status != "DONE")),
        "unread_messages": message_service.unread_count(db, user),
        "unread_notifications": notification_service.unread_count(db, user.id),
        "pending_payouts": money(db.scalar(select(func.coalesce(func.sum(Payout.net_amount), 0)).where(
            Payout.hotel_id.in_(ids), Payout.status == "PENDING"))),
        "upcoming_arrivals": [_short(b) for b in arrivals],
    }


def customer(db: Session, user: User) -> dict:
    today = date.today()
    mine = list(db.scalars(select(Booking).where(Booking.customer_id == user.id)))
    upcoming = sorted([b for b in mine if b.status == BookingStatus.CONFIRMED and b.check_in >= today], key=lambda b: b.check_in)
    current = next((b for b in mine if b.status == BookingStatus.CHECKED_IN), None)
    reviewed = set(db.scalars(select(Review.booking_id).where(Review.customer_id == user.id)))
    loyalty = loyalty_service.get_account(db, user.id)
    db.commit()

    return {
        "current_stay": _short(current) if current else None,
        "upcoming_stays": [_short(b) for b in upcoming[:5]],
        "completed_stays": sum(1 for b in mine if b.status == BookingStatus.CHECKED_OUT),
        "total_spent": money(sum((booking_service.amount_paid(b) for b in mine), 0)),
        "loyalty_points": loyalty.points,
        "loyalty_tier": loyalty.tier,
        "wishlist_count": _count(db, select(func.count(WishlistItem.id)).where(WishlistItem.customer_id == user.id)),
        "unread_notifications": notification_service.unread_count(db, user.id),
        "unread_messages": message_service.unread_count(db, user),
        "waiting_for_review": [_short(b) for b in mine if b.status == BookingStatus.CHECKED_OUT and b.id not in reviewed][:5],
    }


def admin(db: Session) -> dict:
    today = date.today()
    month_start = today.replace(day=1)
    day_start = datetime.combine(today, time.min)
    roles = db.execute(select(Role.name, func.count(User.id)).join(User, User.role_id == Role.id).group_by(Role.name)).all()
    statuses = db.execute(select(Hotel.status, func.count(Hotel.id)).group_by(Hotel.status)).all()
    finance = finance_service.platform_summary(db, month_start, today)

    return {
        "users_by_role": {name: n for name, n in roles},
        "hotels_by_status": {s: n for s, n in statuses},
        "pending_hotel_approvals": dict(statuses).get(HotelStatus.PENDING.value, 0),
        "bookings_created_today": _count(db, select(func.count(Booking.id)).where(Booking.created_at >= day_start)),
        "paid_bookings_this_month": finance["bookings"],
        "gross_booking_value_this_month": finance["gross_booking_value"],
        "platform_income_this_month": finance["platform_income"],
        "active_subscriptions": _count(db, select(func.count(HotelSubscription.id)).where(
            HotelSubscription.status.in_(["ACTIVE", "CANCELLED"]), HotelSubscription.end_date >= today)),
        "open_fraud_flags": _count(db, select(func.count(FraudFlag.id)).where(FraudFlag.status == "OPEN")),
        "failed_logins_24h": _count(db, select(func.count(LoginAttempt.id)).where(
            LoginAttempt.success.is_(False), LoginAttempt.created_at >= utcnow() - timedelta(hours=24))),
        "payouts_pending": finance["payouts_pending"],
    }
