from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import HotelSubscription, RoleName, SubscriptionPlan, User
from app.schemas.subscription import (
    MyPlanOut, PlanCreate, PlanOut, PlanUpdate, SubscribeRequest, SubscribeResponse, SubscriptionOut,
)
from app.services import subscription_service

router = APIRouter(tags=["Subscriptions"])

owner_only = require_roles(RoleName.HOTEL_OWNER)
admin_only = require_roles(RoleName.ADMIN)


@router.get("/subscription-plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    query = select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True))
    return list(db.scalars(query.order_by(SubscriptionPlan.price_monthly)))


@router.post("/subscription-plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(data: PlanCreate, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    return subscription_service.create_plan(db, data)


@router.patch("/subscription-plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, data: PlanUpdate, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    return subscription_service.update_plan(db, subscription_service.get_plan(db, plan_id), data)


@router.post("/subscriptions", response_model=SubscribeResponse, status_code=status.HTTP_201_CREATED)
def subscribe(data: SubscribeRequest, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    sub, client_secret = subscription_service.subscribe(db, user, data.plan_id)
    return {"subscription": sub, "client_secret": client_secret}


@router.get("/subscriptions/my", response_model=MyPlanOut)
def my_plan(user: User = Depends(owner_only), db: Session = Depends(get_db)):
    limit, plan_name = subscription_service.hotel_limit(db, user.id)
    return {
        "plan_name": plan_name,
        "max_hotels": limit,
        "hotels_used": subscription_service.hotels_used(db, user.id),
        "subscription": subscription_service.active_subscription(db, user.id),
    }


@router.get("/subscriptions/history", response_model=list[SubscriptionOut])
def history(user: User = Depends(owner_only), db: Session = Depends(get_db)):
    query = select(HotelSubscription).where(HotelSubscription.owner_id == user.id)
    return list(db.scalars(query.order_by(HotelSubscription.id.desc())))


@router.post("/subscriptions/{sub_id}/test-confirm", response_model=SubscriptionOut)
def test_confirm(sub_id: int, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    sub = subscription_service.get_own_subscription(db, sub_id, user)
    return subscription_service.test_confirm(db, sub)


@router.post("/subscriptions/{sub_id}/cancel", response_model=SubscriptionOut)
def cancel(sub_id: int, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    sub = subscription_service.get_own_subscription(db, sub_id, user)
    return subscription_service.cancel(db, sub)
