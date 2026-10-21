import json
from decimal import Decimal

import stripe
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Booking, BookingStatus, Invoice, Payment, PaymentStatus, Refund, StripeEvent, User,
)
from app.services import availability_service, notification_service
from app.utils.money import money, to_paise
from app.utils.time import utcnow

CURRENCY = "inr"


def _stripe():
    if not settings.stripe_secret_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Stripe is not configured. Add STRIPE_SECRET_KEY (sk_test_...) to .env",
        )
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _stripe_error(err: Exception):
    raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Stripe error: {getattr(err, 'user_message', None) or err}")


# ---------- step 1: start a payment ----------

def create_payment_intent(db: Session, booking: Booking, user: User):
    from app.services.booking_service import expire_if_needed  # local import avoids a circular import

    if booking.customer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your booking")
    expire_if_needed(db, booking)
    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Booking is {booking.status}, not waiting for payment")

    s = _stripe()

    # if the customer clicks "Pay" twice we reuse the same intent instead of making a new one
    existing = db.scalar(
        select(Payment).where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.PENDING.value)
    )
    try:
        if existing:
            intent = s.PaymentIntent.retrieve(existing.provider_payment_id)
            return existing, intent.client_secret

        intent = s.PaymentIntent.create(
            amount=to_paise(booking.total_amount),
            currency=CURRENCY,
            metadata={"booking_id": str(booking.id), "booking_code": booking.booking_code},
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            # same key = Stripe returns the same intent, even if our request is retried
            idempotency_key=f"booking-{booking.id}-intent",
        )
    except stripe.StripeError as err:
        _stripe_error(err)

    payment = Payment(
        booking_id=booking.id,
        amount=booking.total_amount,
        currency=CURRENCY,
        provider_payment_id=intent.id,
        status=PaymentStatus.PENDING.value,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment, intent.client_secret


# ---------- step 2: payment result ----------

def _create_invoice(db: Session, booking: Booking):
    if booking.invoice is not None:
        return
    db.add(Invoice(
        booking_id=booking.id,
        invoice_number=f"INV-{utcnow():%Y%m%d}-{booking.id:06d}",
        subtotal=booking.subtotal,
        discount_amount=booking.discount_amount,
        tax_amount=booking.tax_amount,
        total_amount=booking.total_amount,
    ))


def mark_payment_succeeded(db: Session, provider_payment_id: str) -> bool:
    """Returns False if this intent isn't a booking payment (day 3: could be a subscription)."""
    payment = db.scalar(select(Payment).where(Payment.provider_payment_id == provider_payment_id))
    if payment is None:
        return False
    if payment.status == PaymentStatus.SUCCEEDED:
        return True  # already handled (idempotent)

    payment.status = PaymentStatus.SUCCEEDED.value
    booking = payment.booking

    if booking.status == BookingStatus.CANCELLED:
        # customer cancelled while paying - give the money back
        db.flush()
        refund_booking(db, booking, payment.amount, "Paid after cancellation")
        db.commit()
        return True

    if booking.status in (BookingStatus.PENDING_PAYMENT, BookingStatus.EXPIRED):
        availability_service.lock_room_type(db, booking.room_type_id)

        if not availability_service.room_is_free(db, booking.room_id, booking.check_in, booking.check_out, booking.id):
            # the hold ran out and someone else took the room - try another room of the same type
            others = availability_service.free_rooms(db, booking.room_type_id, booking.check_in, booking.check_out)
            if others:
                booking.room_id = others[0].id
            else:
                db.flush()
                refund_booking(db, booking, payment.amount, "Room no longer available")
                booking.status = BookingStatus.CANCELLED.value
                booking.cancelled_at = utcnow()
                booking.cancelled_by = "SYSTEM"
                booking.cancellation_reason = "Payment arrived after the hold expired and no room was free"
                notification_service.notify(
                    db, booking.customer_id, "Booking could not be confirmed",
                    f"Sorry, the room for {booking.booking_code} was taken before your payment arrived. "
                    "Your money has been refunded.",
                    type="BOOKING", reference=f"booking:{booking.id}",
                )
                db.commit()
                return True

        booking.status = BookingStatus.CONFIRMED.value
        booking.confirmed_at = utcnow()
        booking.expires_at = None
        if booking.coupon is not None:
            booking.coupon.used_count += 1
        _create_invoice(db, booking)
        notification_service.notify(
            db, booking.customer_id, "Booking confirmed",
            f"Your stay at {booking.hotel.name} from {booking.check_in} to {booking.check_out} "
            f"is confirmed. Booking code: {booking.booking_code}",
            type="BOOKING", reference=f"booking:{booking.id}",
        )
        notification_service.notify(
            db, booking.hotel.owner_id, "New booking",
            f"{booking.room_type.name} booked for {booking.check_in} to {booking.check_out} "
            f"({booking.booking_code}).",
            type="BOOKING", reference=f"booking:{booking.id}",
        )

    db.commit()
    return True


def mark_payment_failed(db: Session, provider_payment_id: str, reason: str | None) -> bool:
    payment = db.scalar(select(Payment).where(Payment.provider_payment_id == provider_payment_id))
    if payment is None:
        return False
    if payment.status == PaymentStatus.PENDING:
        payment.status = PaymentStatus.FAILED.value
        payment.failure_reason = (reason or "Payment failed")[:255]
        db.commit()
    return True


def handle_webhook(db: Session, payload: bytes, signature: str | None) -> str:
    if not settings.stripe_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "STRIPE_WEBHOOK_SECRET is not set")

    # 1. prove the request really came from Stripe (anyone can POST to our URL)
    try:
        stripe.Webhook.construct_event(payload, signature or "", settings.stripe_webhook_secret)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")

    event = json.loads(payload)

    # 2. idempotency: Stripe retries webhooks, so ignore events we've seen
    if db.scalar(select(StripeEvent).where(StripeEvent.event_id == event["id"])):
        return "duplicate"

    obj = event["data"]["object"]
    event_type = event["type"]

    from app.services import subscription_service  # local import avoids a circular import

    if event_type == "payment_intent.succeeded":
        # the same Stripe account takes booking payments and plan payments
        if not mark_payment_succeeded(db, obj["id"]):
            subscription_service.activate_by_intent(db, obj["id"])
    elif event_type == "payment_intent.payment_failed":
        error = obj.get("last_payment_error") or {}
        if not mark_payment_failed(db, obj["id"], error.get("message")):
            subscription_service.fail_by_intent(db, obj["id"])
    elif event_type in ("refund.updated", "refund.created"):
        refund = db.scalar(select(Refund).where(Refund.provider_refund_id == obj["id"]))
        if refund:
            refund.status = {"succeeded": "SUCCEEDED", "failed": "FAILED"}.get(obj.get("status"), "PENDING")

    db.add(StripeEvent(event_id=event["id"], event_type=event_type))
    db.commit()
    return "processed"


def test_confirm(db: Session, payment: Payment, user: User) -> str:
    """Only for local testing: pays the intent with Stripe's test Visa card."""
    if not settings.debug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if payment.booking.customer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your payment")

    s = _stripe()
    try:
        intent = s.PaymentIntent.confirm(payment.provider_payment_id, payment_method="pm_card_visa")
    except stripe.StripeError as err:
        _stripe_error(err)

    # in production the webhook does this; here we also do it directly so you
    # can test without running the Stripe CLI. It's safe to run twice.
    if intent.status == "succeeded":
        mark_payment_succeeded(db, intent.id)
    return intent.status


# ---------- refunds ----------

def refund_booking(db: Session, booking: Booking, amount: Decimal, reason: str) -> Refund:
    payment = next(
        (p for p in reversed(booking.payments)
         if p.status in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED)),
        None,
    )
    if payment is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No successful payment to refund")

    s = _stripe()
    try:
        stripe_refund = s.Refund.create(
            payment_intent=payment.provider_payment_id,
            amount=to_paise(amount),
            metadata={"booking_id": str(booking.id)},
            idempotency_key=f"refund-booking-{booking.id}-{to_paise(amount)}",
        )
    except stripe.StripeError as err:
        _stripe_error(err)

    refund = Refund(
        payment_id=payment.id,
        booking_id=booking.id,
        amount=money(amount),
        provider_refund_id=stripe_refund.id,
        status="SUCCEEDED" if stripe_refund.status == "succeeded" else "PENDING",
        reason=reason[:255],
    )
    db.add(refund)
    payment.status = (
        PaymentStatus.REFUNDED.value if money(amount) >= payment.amount else PaymentStatus.PARTIALLY_REFUNDED.value
    )
    return refund  # the caller commits


def invoice_data(booking: Booking) -> dict:
    invoice = booking.invoice
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No invoice yet - the booking isn't paid")

    last_payment = booking.payments[-1] if booking.payments else None
    hotel = booking.hotel
    return {
        "invoice_number": invoice.invoice_number,
        "issued_at": invoice.issued_at,
        "booking_code": booking.booking_code,
        "customer_name": booking.customer.full_name,
        "customer_email": booking.customer.email,
        "hotel_name": hotel.name,
        "hotel_address": f"{hotel.address_line}, {hotel.city}",
        "room_type": booking.room_type.name,
        "room_number": booking.room.room_number,
        "check_in": booking.check_in,
        "check_out": booking.check_out,
        "nights": booking.nights,
        "room_rate": booking.room_rate,
        "subtotal": invoice.subtotal,
        "discount_amount": invoice.discount_amount,
        "tax_amount": invoice.tax_amount,
        "total_amount": invoice.total_amount,
        "payment_status": last_payment.status if last_payment else "NONE",
    }
