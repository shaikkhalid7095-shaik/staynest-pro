from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import RoleName, User
from app.services import analytics_service, dashboard_service, insights_service

router = APIRouter(tags=["Analytics & Dashboards"])

owner_or_admin = require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)


def _range(start: date | None, end: date | None, default_days: int = 30) -> tuple[date, date]:
    end = end or date.today()
    start = start or end - timedelta(days=default_days)
    analytics_service.check_range(start, end)
    return start, end


# hotel_id is optional: leave it empty to see all your hotels (or all hotels, for admin)

@router.get("/analytics/revenue")
def revenue(
    hotel_id: int | None = None, start: date | None = None, end: date | None = None,
    group_by: Literal["day", "month"] = "day",
    user: User = Depends(owner_or_admin), db: Session = Depends(get_db),
):
    start, end = _range(start, end)
    ids = analytics_service.hotel_ids_for(db, user, hotel_id)
    return analytics_service.revenue(db, ids, start, end, group_by)


@router.get("/analytics/occupancy")
def occupancy(
    hotel_id: int | None = None, start: date | None = None, end: date | None = None,
    user: User = Depends(owner_or_admin), db: Session = Depends(get_db),
):
    start, end = _range(start, end)
    return analytics_service.occupancy(db, analytics_service.hotel_ids_for(db, user, hotel_id), start, end)


@router.get("/analytics/customers")
def customers(
    hotel_id: int | None = None, start: date | None = None, end: date | None = None,
    user: User = Depends(owner_or_admin), db: Session = Depends(get_db),
):
    start, end = _range(start, end, default_days=90)
    return insights_service.customers(db, analytics_service.hotel_ids_for(db, user, hotel_id), start, end)


@router.get("/bi/overview")
def bi_overview(
    hotel_id: int | None = None, start: date | None = None, end: date | None = None,
    user: User = Depends(owner_or_admin), db: Session = Depends(get_db),
):
    start, end = _range(start, end, default_days=180)
    return insights_service.overview(db, analytics_service.hotel_ids_for(db, user, hotel_id), start, end)


@router.get("/dashboard/owner")
def owner_dashboard(user: User = Depends(require_roles(RoleName.HOTEL_OWNER)), db: Session = Depends(get_db)):
    return dashboard_service.owner(db, user)


@router.get("/dashboard/customer")
def customer_dashboard(user: User = Depends(require_roles(RoleName.CUSTOMER)), db: Session = Depends(get_db)):
    return dashboard_service.customer(db, user)


@router.get("/dashboard/admin")
def admin_dashboard(_: User = Depends(require_roles(RoleName.ADMIN)), db: Session = Depends(get_db)):
    return dashboard_service.admin(db)
