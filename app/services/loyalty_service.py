import secrets
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Coupon, LoyaltyAccount, LoyaltyTransaction, User
from app.services import audit_service, notification_service, settings_service
from app.utils.money import money
from app.utils.time import utcnow

# lifetime points needed for each tier, and the earning bonus it gives
TIERS = [("PLATINUM", 5000, Decimal("1.5")), ("GOLD", 1000, Decimal("1.25")), ("SILVER", 0, Decimal("1"))]
MIN_REDEEM = 100
COUPON_DAYS = 90


def tier_for(lifetime_points: int) -> str:
    for name, needed, _ in TIERS:
        if lifetime_points >= needed:
            return name
    return "SILVER"


def multiplier(tier: str) -> Decimal:
    return next(m for name, _, m in TIERS if name == tier)


def get_account(db: Session, user_id: int) -> LoyaltyAccount:
    account = db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.user_id == user_id))
    if account is None:
        account = LoyaltyAccount(user_id=user_id, points=0, lifetime_points=0, tier="SILVER")
        db.add(account)
        db.flush()
    return account


def _add(db: Session, account: LoyaltyAccount, points: int, kind: str, note: str, booking_id: int | None = None):
    account.points += points
    if points > 0:
        account.lifetime_points += points
        account.tier = tier_for(account.lifetime_points)
    db.add(LoyaltyTransaction(user_id=account.user_id, booking_id=booking_id, points=points, type=kind, note=note))


def earn_for_booking(db: Session, booking: Booking) -> int:
    """Called at check-out. Adds points but doesn't commit - check-out does."""
    already = db.scalar(select(LoyaltyTransaction.id).where(
        LoyaltyTransaction.booking_id == booking.id, LoyaltyTransaction.type == "EARN"
    ))
    if already:
        return 0

    account = get_account(db, booking.customer_id)
    room_spend = booking.subtotal - booking.discount_amount  # taxes don't earn points
    per_100 = settings_service.get_int(db, "loyalty_points_per_100")
    points = int(room_spend / 100 * per_100 * multiplier(account.tier))
    if points <= 0:
        return 0

    _add(db, account, points, "EARN", f"Stay {booking.booking_code}", booking.id)
    notification_service.notify(
        db, booking.customer_id, f"You earned {points} points",
        f"Your balance is {account.points} points ({account.tier}).", type="LOYALTY",
    )
    return points


def redeem(db: Session, user: User, points: int) -> dict:
    if points < MIN_REDEEM:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Redeem at least {MIN_REDEEM} points")
    account = get_account(db, user.id)
    if points > account.points:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You only have {account.points} points")

    value = money(points * settings_service.get_decimal(db, "loyalty_rupees_per_point"))
    code = "LOYAL-" + secrets.token_hex(4).upper()
    now = utcnow()
    # a one-time coupon: works on any hotel, once
    db.add(Coupon(
        code=code, description=f"Loyalty reward for {user.email}", discount_type="FLAT", discount_value=value,
        min_booking_amount=0, valid_from=now, valid_until=now + timedelta(days=COUPON_DAYS),
        usage_limit=1, used_count=0, per_user_limit=1, created_by_id=user.id, is_active=True,
    ))
    _add(db, account, -points, "REDEEM", f"Coupon {code}")
    db.commit()
    return {"coupon_code": code, "value": value, "points_used": points, "points_left": account.points,
            "valid_until": now + timedelta(days=COUPON_DAYS)}


def summary(db: Session, user: User) -> dict:
    account = get_account(db, user.id)
    db.commit()
    history = list(db.scalars(
        select(LoyaltyTransaction).where(LoyaltyTransaction.user_id == user.id)
        .order_by(LoyaltyTransaction.id.desc()).limit(20)
    ))
    next_tier = next(((name, needed) for name, needed, _ in reversed(TIERS) if needed > account.lifetime_points), None)
    return {
        "points": account.points,
        "lifetime_points": account.lifetime_points,
        "tier": account.tier,
        "next_tier": next_tier[0] if next_tier else None,
        "points_to_next_tier": next_tier[1] - account.lifetime_points if next_tier else 0,
        "history": history,
    }


def adjust(db: Session, user_id: int, points: int, note: str, admin: User, ip: str | None) -> LoyaltyAccount:
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    account = get_account(db, user_id)
    if account.points + points < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Balance can't go below zero")
    _add(db, account, points, "ADJUST", note)
    audit_service.log(db, admin.id, "LOYALTY_ADJUSTED", "user", user_id, f"{points:+d}: {note}", ip)
    db.commit()
    db.refresh(account)
    return account
