from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models import Payment, RoleName, User
from app.schemas.payment import CreateIntentRequest, CreateIntentResponse, PaymentOut, TestConfirmResponse
from app.services import booking_service, payment_service

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-intent", response_model=CreateIntentResponse)
def create_intent(
    data: CreateIntentRequest,
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    booking = booking_service.get_booking_for_user(db, data.booking_id, user)
    payment, client_secret = payment_service.create_payment_intent(db, booking, user)
    return CreateIntentResponse(
        payment_id=payment.id,
        payment_intent_id=payment.provider_payment_id,
        client_secret=client_secret,
        amount=payment.amount,
        currency=payment.currency,
    )


@router.post("/{payment_id}/test-confirm", response_model=TestConfirmResponse)
def test_confirm(
    payment_id: int,
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    stripe_status = payment_service.test_confirm(db, payment, user)
    db.refresh(payment.booking)
    return TestConfirmResponse(payment_id=payment.id, stripe_status=stripe_status, booking_status=payment.booking.status)


@router.post("/webhook", include_in_schema=True)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    # no login here - Stripe calls this. The signature check is the security.
    payload = await request.body()  # must be the raw bytes, or the signature won't match
    signature = request.headers.get("stripe-signature")
    result = payment_service.handle_webhook(db, payload, signature)
    return {"status": result}


@router.get("/booking/{booking_id}", response_model=list[PaymentOut])
def booking_payments(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return booking_service.get_booking_for_user(db, booking_id, user).payments