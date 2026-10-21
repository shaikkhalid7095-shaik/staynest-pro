"""33 customer analytics and 47 business intelligence."""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Hotel, RoomType, User
from app.services.analytics_service import PAID, _bookings, _kept_amount
from app.utils.money import money

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _mask(email: str) -> str:
    # owners see who their best guests are, but not the full email
    name, _, domain = email.partition("@")
    return f"{name[:2]}***@{domain}"


# ---------- 33. customers ----------

def customers(db: Session, hotel_ids: list[int], start: date, end: date) -> dict:
    bookings = _bookings(db, hotel_ids, start, end, PAID)
    spend, stays = defaultdict(Decimal), Counter()
    for b in bookings:
        spend[b.customer_id] += b.total_amount
        stays[b.customer_id] += 1

    # "returning" = booked these hotels before this period too
    earlier = set(db.scalars(select(Booking.customer_id).where(
        Booking.hotel_id.in_(hotel_ids or [-1]), Booking.check_in < start, Booking.status.in_(PAID)
    )))
    customer_ids = set(spend)
    returning = customer_ids & earlier

    top = sorted(spend.items(), key=lambda kv: kv[1], reverse=True)[:5]
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_([uid for uid, _ in top] or [-1])))}
    nights = sum(b.nights for b in bookings)

    return {
        "start": start, "end": end,
        "unique_customers": len(customer_ids),
        "new_customers": len(customer_ids - earlier),
        "returning_customers": len(returning),
        "repeat_rate_percent": round(len(returning) / len(customer_ids) * 100, 1) if customer_ids else 0.0,
        "bookings": len(bookings),
        "avg_spend_per_customer": money(sum(spend.values(), Decimal("0")) / len(customer_ids)) if customer_ids else Decimal("0.00"),
        "avg_nights_per_stay": round(nights / len(bookings), 1) if bookings else 0.0,
        "avg_guests_per_booking": round(sum(b.adults + b.children for b in bookings) / len(bookings), 1) if bookings else 0.0,
        "top_customers": [
            {"name": users[uid].full_name, "email": _mask(users[uid].email), "stays": stays[uid], "spent": money(total)}
            for uid, total in top
        ],
    }


# ---------- 47. business intelligence ----------

def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def overview(db: Session, hotel_ids: list[int], start: date, end: date) -> dict:
    all_bookings = _bookings(db, hotel_ids, start, end)
    useful = [b for b in all_bookings if b.status != BookingStatus.EXPIRED]  # unpaid holds aren't real demand

    monthly = defaultdict(lambda: {"bookings": 0, "cancelled": 0, "revenue": Decimal("0")})
    for b in useful:
        row = monthly[_month_key(b.check_in)]
        row["bookings"] += 1
        if b.status == BookingStatus.CANCELLED:
            row["cancelled"] += 1
        row["revenue"] += _kept_amount(b)

    trend = [{
        "month": k, "bookings": r["bookings"], "cancelled": r["cancelled"],
        "cancellation_rate_percent": round(r["cancelled"] / r["bookings"] * 100, 1) if r["bookings"] else 0.0,
        "revenue": money(r["revenue"]),
    } for k, r in sorted(monthly.items())]

    paid = [b for b in useful if b.status in PAID]
    lead_days = [(b.check_in - b.created_at.date()).days for b in paid if b.created_at]
    weekday_nights = Counter()
    for b in paid:
        for i in range(b.nights):
            weekday_nights[WEEKDAYS[(b.check_in + timedelta(days=i)).weekday()]] += 1

    hotels = {h.id: h for h in db.scalars(select(Hotel).where(Hotel.id.in_(hotel_ids or [-1])))}
    city_revenue = defaultdict(Decimal)
    for b in paid:
        city_revenue[hotels[b.hotel_id].city] += b.total_amount

    types = {t.id: t for t in db.scalars(select(RoomType).where(RoomType.hotel_id.in_(hotel_ids or [-1])))}
    by_type = defaultdict(lambda: {"bookings": 0, "nights": 0, "revenue": Decimal("0")})
    for b in paid:
        row = by_type[b.room_type_id]
        row["bookings"] += 1
        row["nights"] += b.nights
        row["revenue"] += b.subtotal - b.discount_amount

    cancelled = sum(1 for b in useful if b.status == BookingStatus.CANCELLED)
    return {
        "start": start, "end": end,
        "total_bookings": len(useful),
        "cancellation_rate_percent": round(cancelled / len(useful) * 100, 1) if useful else 0.0,
        "avg_lead_time_days": round(sum(lead_days) / len(lead_days), 1) if lead_days else 0.0,
        "avg_length_of_stay": round(sum(b.nights for b in paid) / len(paid), 1) if paid else 0.0,
        "monthly_trend": trend,
        "nights_by_weekday": [{"weekday": d, "nights": weekday_nights[d]} for d in WEEKDAYS],
        "top_cities": [{"city": c, "revenue": money(v)} for c, v in sorted(city_revenue.items(), key=lambda kv: kv[1], reverse=True)[:5]],
        "room_type_performance": sorted([{
            "room_type_id": tid, "hotel_id": types[tid].hotel_id, "name": types[tid].name,
            "bookings": r["bookings"], "room_nights": r["nights"], "room_revenue": money(r["revenue"]),
            "avg_nightly_rate": money(r["revenue"] / r["nights"]) if r["nights"] else Decimal("0.00"),
        } for tid, r in by_type.items()], key=lambda r: r["room_revenue"], reverse=True),
    }
