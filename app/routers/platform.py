"""38 reports, 43 loyalty, 44 locations, 45 calendar, 46 finance, 49 public settings."""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import RoleName, User
from app.schemas.admin import (
    LoyaltyAdjust, LoyaltySummary, PayoutCreate, PayoutOut, PayoutPaid, RedeemRequest, RedeemResponse,
)
from app.services import (
    analytics_service, audit_service, finance_service, hotel_service, location_service, loyalty_service,
    report_service, room_service, settings_service, staff_service,
)

router = APIRouter()

owner_or_admin = require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)
admin_only = require_roles(RoleName.ADMIN)


def _csv(text: str, name: str) -> Response:
    return Response(text, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- 38. reports ----------

@router.get("/reports/bookings.csv", tags=["Reports & Export"])
def bookings_report(hotel_id: int | None = None, start: date | None = None, end: date | None = None,
                    user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    end = end or date.today()
    start = start or end - timedelta(days=30)
    analytics_service.check_range(start, end)
    ids = analytics_service.hotel_ids_for(db, user, hotel_id)
    return _csv(report_service.bookings_csv(db, ids, start, end), f"bookings_{start}_{end}.csv")


@router.get("/reports/revenue.csv", tags=["Reports & Export"])
def revenue_report(hotel_id: int | None = None, start: date | None = None, end: date | None = None,
                   group_by: Literal["day", "month"] = "month",
                   user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    end = end or date.today()
    start = start or end - timedelta(days=180)
    analytics_service.check_range(start, end)
    ids = analytics_service.hotel_ids_for(db, user, hotel_id)
    return _csv(report_service.revenue_csv(db, ids, start, end, group_by), f"revenue_{start}_{end}.csv")


@router.get("/reports/payouts.csv", tags=["Reports & Export"])
def payouts_report(hotel_id: int | None = None, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    ids = analytics_service.hotel_ids_for(db, user, hotel_id)
    return _csv(report_service.payouts_csv(db, ids), "payouts.csv")


# ---------- 43. loyalty ----------

@router.get("/loyalty/me", response_model=LoyaltySummary, tags=["Loyalty & Rewards"])
def my_points(user: User = Depends(require_roles(RoleName.CUSTOMER)), db: Session = Depends(get_db)):
    return loyalty_service.summary(db, user)


@router.post("/loyalty/redeem", response_model=RedeemResponse, tags=["Loyalty & Rewards"])
def redeem(data: RedeemRequest, user: User = Depends(require_roles(RoleName.CUSTOMER)), db: Session = Depends(get_db)):
    return loyalty_service.redeem(db, user, data.points)


@router.post("/admin/loyalty/adjust", tags=["Loyalty & Rewards"])
def adjust_points(data: LoyaltyAdjust, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    account = loyalty_service.adjust(db, data.user_id, data.points, data.note, admin, audit_service.client_ip(request))
    return {"user_id": account.user_id, "points": account.points, "tier": account.tier}


# ---------- 44. locations ----------

@router.get("/locations/nearby", tags=["Location Services"])
def nearby(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180),
           radius_km: float = Query(10, gt=0, le=500), limit: int = Query(20, ge=1, le=100),
           db: Session = Depends(get_db)):
    return location_service.nearby(db, lat, lng, radius_km, limit)


@router.get("/locations/cities", tags=["Location Services"])
def cities(db: Session = Depends(get_db)):
    return location_service.cities(db)


@router.get("/locations/hotels/{hotel_id}/distance", tags=["Location Services"])
def distance(hotel_id: int, lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180),
             db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    if hotel.latitude is None or hotel.longitude is None:
        return {"hotel_id": hotel.id, "distance_km": None, "note": "This hotel hasn't added its location"}
    return {"hotel_id": hotel.id, "distance_km": location_service.distance_km(lat, lng, float(hotel.latitude), float(hotel.longitude))}


# ---------- 45. calendar & scheduler ----------

@router.get("/hotels/{hotel_id}/calendar", tags=["Calendar & Scheduler"])
def room_calendar(hotel_id: int, start: date | None = None, days: int = Query(14, ge=1, le=62),
                  user: User = Depends(require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN, RoleName.HOTEL_STAFF)),
                  db: Session = Depends(get_db)):
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    return location_service.room_calendar(db, hotel, start or date.today(), days)


@router.get("/hotels/{hotel_id}/room-types/{type_id}/next-available", tags=["Calendar & Scheduler"])
def next_available(hotel_id: int, type_id: int, nights: int = Query(1, ge=1, le=30),
                   from_date: date | None = None, search_days: int = Query(60, ge=1, le=180),
                   options: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    room_type = room_service.get_room_type(db, hotel, type_id)
    return location_service.next_available(db, room_type, nights, from_date or date.today(), search_days, options)


# ---------- 46. finance ----------

@router.get("/finance/hotels/{hotel_id}/summary", tags=["Financial Management"])
def hotel_finance(hotel_id: int, start: date | None = None, end: date | None = None,
                  user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    hotel = hotel_service.get_manageable_hotel(db, hotel_id, user)
    end = end or date.today()
    start = start or end.replace(day=1)
    analytics_service.check_range(start, end)
    return finance_service.hotel_summary(db, hotel, start, end)


@router.get("/finance/payouts", response_model=list[PayoutOut], tags=["Financial Management"])
def payouts(hotel_id: int | None = None, user: User = Depends(owner_or_admin), db: Session = Depends(get_db)):
    return finance_service.list_payouts(db, user, hotel_id)


@router.post("/admin/payouts", response_model=PayoutOut, status_code=status.HTTP_201_CREATED, tags=["Financial Management"])
def create_payout(data: PayoutCreate, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    hotel = hotel_service.get_hotel_or_404(db, data.hotel_id)
    return finance_service.create_payout(db, hotel, data.period_start, data.period_end, admin, audit_service.client_ip(request))


@router.patch("/admin/payouts/{payout_id}/paid", response_model=PayoutOut, tags=["Financial Management"])
def mark_paid(payout_id: int, data: PayoutPaid, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return finance_service.mark_paid(db, payout_id, data.reference, admin, audit_service.client_ip(request))


@router.get("/admin/finance/summary", tags=["Financial Management"])
def platform_finance(start: date | None = None, end: date | None = None,
                     _: User = Depends(admin_only), db: Session = Depends(get_db)):
    end = end or date.today()
    start = start or end.replace(day=1)
    analytics_service.check_range(start, end)
    return finance_service.platform_summary(db, start, end)


# ---------- 49. public settings ----------

@router.get("/settings/public", tags=["System Configuration"])
def public_settings(db: Session = Depends(get_db)):
    return {s["key"]: s["value"] for s in settings_service.list_all(db, public_only=True)}
