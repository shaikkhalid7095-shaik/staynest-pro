from datetime import date, timedelta

import stripe
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Hotel, HotelSubscription, SubscriptionPayment, SubscriptionPlan, User
from app.schemas.subscription import PlanCreate, PlanUpdate
from app.services import notification_service
from app.utils.money import to_paise

FREE_HOTEL_LIMIT = 1   # owners without a plan can list one hotel
PERIOD_DAYS = 30


# ---------- plans (admin) ----------

def create_plan(db: Session, data: PlanCreate) -> SubscriptionPlan:
    if db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.name == data.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A plan with this name already exists")
    plan = SubscriptionPlan(**data.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def get_plan(db: Session, plan_id: int) -> SubscriptionPlan:
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    return plan


def update_plan(db: Session, plan: SubscriptionPlan, data: PlanUpdate) -> SubscriptionPlan:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    return plan


# ---------- what an owner currently has ----------

def active_subscription(db: Session, owner_id: int) -> HotelSubscription | None:
    return db.scalar(
        select(HotelSubscription)
        .where(
            HotelSubscription.owner_id == owner_id,
            HotelSubscription.status.in_(["ACTIVE", "CANCELLED"]),  # cancelled still runs till end_date
            HotelSubscription.end_date >= date.today(),
        )
        .order_by(HotelSubscription.id.desc())
        .limit(1)
    )


def hotel_limit(db: Session, owner_id: int) -> tuple[int, str]:
    sub = active_subscription(db, owner_id)
    if sub is None:
        return FREE_HOTEL_LIMIT, "free"
    return sub.plan.max_hotels, sub.plan.name


def hotels_used(db: Session, owner_id: int) -> int:
    return db.scalar(
        select(func.count(Hotel.id)).where(Hotel.owner_id == owner_id, Hotel.is_active.is_(True))
    ) or 0


# ---------- subscribe & pay ----------

def _stripe():
    if settings.stripe_mock:  # no Stripe account (India sign-up is invite-only)
        from app.core import fake_stripe
        return fake_stripe
    if not settings.stripe_secret_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Stripe is not configured. Add STRIPE_SECRET_KEY (sk_test_...) to .env",
        )
    stripe.api_key = settings.stripe_secret_key
    return stripe


def activate(db: Session, sub: HotelSubscription):
    # a new plan replaces whatever the owner had before
    old_ones = db.scalars(
        select(HotelSubscription).where(
            HotelSubscription.owner_id == sub.owner_id,
            HotelSubscription.id != sub.id,
            HotelSubscription.status.in_(["ACTIVE", "CANCELLED"]),
        )
    )
    for old in old_ones:
        old.status = "EXPIRED"
        old.end_date = date.today()

    sub.status = "ACTIVE"
    sub.start_date = date.today()
    sub.end_date = date.today() + timedelta(days=PERIOD_DAYS)
    notification_service.notify(
        db, sub.owner_id, "Subscription active",
        f"Your {sub.plan.name} plan is active until {sub.end_date}.",
        type="SUBSCRIPTION", reference=f"subscription:{sub.id}",
    )


def subscribe(db: Session, owner: User, plan_id: int):
    plan = get_plan(db, plan_id)
    if not plan.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This plan is no longer offered")

    current = active_subscription(db, owner.id)
    if current and current.plan_id == plan.id and current.status == "ACTIVE":
        raise HTTPException(status.HTTP_409_CONFLICT, f"You are already on the {plan.name} plan")
    if plan.max_hotels < hotels_used(db, owner.id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{plan.name} allows {plan.max_hotels} hotel(s) but you have {hotels_used(db, owner.id)}",
        )

    sub = HotelSubscription(owner_id=owner.id, plan_id=plan.id, status="PENDING")
    db.add(sub)
    db.flush()  # gives sub an id without committing

    if plan.price_monthly == 0:
        activate(db, sub)
        db.commit()
        db.refresh(sub)
        return sub, None

    s = _stripe()
    try:
        intent = s.PaymentIntent.create(
            amount=to_paise(plan.price_monthly),
            currency="inr",
            metadata={"type": "subscription", "subscription_id": str(sub.id)},
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            idempotency_key=f"subscription-{sub.id}",
        )
    except stripe.StripeError as err:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Stripe error: {getattr(err, 'user_message', None) or err}")

    db.add(SubscriptionPayment(
        subscription_id=sub.id, amount=plan.price_monthly, provider_payment_id=intent.id,
    ))
    db.commit()
    db.refresh(sub)
    return sub, intent.client_secret


def activate_by_intent(db: Session, intent_id: str) -> bool:
    """Called from the Stripe webhook. Returns False if this intent isn't a subscription."""
    payment = db.scalar(select(SubscriptionPayment).where(SubscriptionPayment.provider_payment_id == intent_id))
    if payment is None:
        return False
    if payment.status != "SUCCEEDED":
        payment.status = "SUCCEEDED"
        if payment.subscription.status == "PENDING":
            activate(db, payment.subscription)
        db.commit()
    return True


def fail_by_intent(db: Session, intent_id: str) -> bool:
    payment = db.scalar(select(SubscriptionPayment).where(SubscriptionPayment.provider_payment_id == intent_id))
    if payment is None:
        return False
    if payment.status == "PENDING":
        payment.status = "FAILED"
        db.commit()
    return True


def get_own_subscription(db: Session, sub_id: int, owner: User) -> HotelSubscription:
    sub = db.get(HotelSubscription, sub_id)
    if sub is None or sub.owner_id != owner.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    return sub


def test_confirm(db: Session, sub: HotelSubscription) -> HotelSubscription:
    """Local testing only: pays with Stripe's test Visa card, like /payments/{id}/test-confirm."""
    if not settings.debug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    pending = next((p for p in sub.payments if p.status == "PENDING"), None)
    if pending is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to pay for this subscription")

    s = _stripe()
    try:
        intent = s.PaymentIntent.confirm(pending.provider_payment_id, payment_method="pm_card_visa")
    except stripe.StripeError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Stripe error: {getattr(err, 'user_message', None) or err}")

    if intent.status == "succeeded":
        activate_by_intent(db, intent.id)
    db.refresh(sub)
    return sub


def cancel(db: Session, sub: HotelSubscription) -> HotelSubscription:
    if sub.status == "PENDING":
        sub.status = "CANCELLED"
    elif sub.status == "ACTIVE":
        # stays usable until end_date, it just won't renew
        sub.status = "CANCELLED"
        sub.auto_renew = False
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A {sub.status} subscription can't be cancelled")
    db.commit()
    db.refresh(sub)
    return sub
