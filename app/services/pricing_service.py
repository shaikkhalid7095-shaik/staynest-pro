from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session

from app.models import Booking, BookingStatus, Coupon, PricingRule, RoomType
from app.utils.money import money
from app.utils.time import utcnow

# GST on hotel rooms in India: 12% up to Rs 7,500 per night, 18% above that
GST_LIMIT = Decimal("7500")
GST_LOW = Decimal("0.12")
GST_HIGH = Decimal("0.18")

MAX_DISCOUNT_PERCENT = Decimal("-90")  # rules can't make a room (almost) free


def tax_rate_for(rate_per_night: Decimal) -> Decimal:
    return GST_LOW if rate_per_night <= GST_LIMIT else GST_HIGH


# ---------- dynamic pricing (day 3) ----------

def rules_for(room_type: RoomType) -> list[PricingRule]:
    # object_session gives us the db session the room type was loaded with,
    # so callers don't have to pass db around just for pricing
    db = object_session(room_type)
    return list(db.scalars(
        select(PricingRule).where(
            PricingRule.hotel_id == room_type.hotel_id,
            PricingRule.is_active.is_(True),
            or_(PricingRule.room_type_id.is_(None), PricingRule.room_type_id == room_type.id),
        )
    ))


def rule_applies(rule: PricingRule, night: date) -> bool:
    if rule.start_date and night < rule.start_date:
        return False
    if rule.end_date and night > rule.end_date:
        return False
    if rule.days_of_week:
        days = {int(d) for d in rule.days_of_week.split(",")}
        if night.weekday() not in days:
            return False
    return True


def price_for_night(room_type: RoomType, night: date, rules: list[PricingRule]) -> tuple[Decimal, list[str]]:
    matched = [r for r in rules if rule_applies(r, night)]
    percent = sum((r.adjustment_percent for r in matched), Decimal("0"))
    percent = max(percent, MAX_DISCOUNT_PERCENT)
    price = money(room_type.base_price * (100 + percent) / 100)
    return price, [r.name for r in matched]


def nightly_rate(room_type: RoomType, night: date) -> Decimal:
    price, _ = price_for_night(room_type, night, rules_for(room_type))
    return price


def stay_price(room_type: RoomType, check_in: date, check_out: date) -> Decimal:
    """Total room price for the stay - every night priced on its own."""
    rules = rules_for(room_type)
    total = Decimal("0")
    night = check_in
    while night < check_out:
        price, _ = price_for_night(room_type, night, rules)
        total += price
        night += timedelta(days=1)
    return money(total)


def price_calendar(room_type: RoomType, start: date, days: int) -> list[dict]:
    rules = rules_for(room_type)
    result = []
    for i in range(days):
        night = start + timedelta(days=i)
        price, applied = price_for_night(room_type, night, rules)
        result.append({"date": night, "weekday": night.strftime("%A"), "price": price, "rules_applied": applied})
    return result


# ---------- coupons ----------

def coupon_discount(db: Session, code: str, hotel_id: int, customer_id: int, amount: Decimal):
    """Check every coupon rule. Returns (coupon, discount) or raises 400."""
    coupon = db.scalar(select(Coupon).where(Coupon.code == code.strip().upper()))
    now = utcnow()

    def reject(msg):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Coupon not valid: {msg}")

    if coupon is None or not coupon.is_active:
        reject("code not found")
    if now < coupon.valid_from:
        reject("not started yet")
    if now > coupon.valid_until:
        reject("expired")
    if coupon.hotel_id is not None and coupon.hotel_id != hotel_id:
        reject("this coupon is for a different hotel")
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        reject("usage limit reached")
    if amount < coupon.min_booking_amount:
        reject(f"minimum booking amount is {coupon.min_booking_amount}")

    times_used = db.scalar(
        select(func.count(Booking.id)).where(
            Booking.coupon_id == coupon.id,
            Booking.customer_id == customer_id,
            Booking.status.in_([
                BookingStatus.CONFIRMED.value,
                BookingStatus.CHECKED_IN.value,
                BookingStatus.CHECKED_OUT.value,
            ]),
        )
    )
    if times_used >= coupon.per_user_limit:
        reject("you have already used this coupon")

    if coupon.discount_type == "PERCENT":
        discount = amount * coupon.discount_value / 100
        if coupon.max_discount is not None:
            discount = min(discount, coupon.max_discount)
    else:
        discount = coupon.discount_value

    # a discount can never make the price negative
    return coupon, money(min(discount, amount))


# ---------- final bill ----------

def calculate(subtotal: Decimal, nights: int, discount: Decimal = Decimal("0")) -> dict:
    # average nightly rate decides the GST slab
    avg_rate = money(subtotal / nights)
    taxable = subtotal - discount
    tax = money(taxable * tax_rate_for(avg_rate))
    return {
        "room_rate": avg_rate,
        "subtotal": money(subtotal),
        "discount_amount": money(discount),
        "tax_amount": tax,
        "total_amount": money(taxable + tax),
    }
