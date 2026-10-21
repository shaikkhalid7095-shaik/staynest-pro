from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import HotelStatus, RoleName, User
from app.schemas.admin import (
    AdminCreate, AuditLogOut, FraudFlagOut, FraudReview, HotelModeration, SettingOut, SettingUpdate,
    UserPage, UserStatusUpdate,
)
from app.schemas.hotel import HotelOut
from app.schemas.user import UserOut
from app.services import admin_service, audit_service, fraud_service, hotel_service, settings_service

router = APIRouter(prefix="/admin", tags=["Admin"])

admin_only = require_roles(RoleName.ADMIN)
ip_of = audit_service.client_ip


# ---------- 50. users ----------

@router.get("/users", response_model=UserPage)
def list_users(
    role: Literal["CUSTOMER", "HOTEL_OWNER", "HOTEL_STAFF", "ADMIN"] | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(admin_only), db: Session = Depends(get_db),
):
    result = admin_service.list_users(db, role, is_active, search, page, size)
    result["items"] = [UserOut.from_user(u) for u in result["items"]]
    return result


@router.get("/users/{user_id}")
def user_details(user_id: int, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = admin_service.get_user(db, user_id)
    return {"user": UserOut.from_user(user), **admin_service.user_details(db, user)}


@router.patch("/users/{user_id}/status", response_model=UserOut)
def block_or_unblock(
    user_id: int, data: UserStatusUpdate, request: Request,
    admin: User = Depends(admin_only), db: Session = Depends(get_db),
):
    target = admin_service.get_user(db, user_id)
    return UserOut.from_user(admin_service.set_active(db, target, data.is_active, data.reason, admin, ip_of(request)))


@router.post("/users/{user_id}/force-logout", status_code=status.HTTP_204_NO_CONTENT)
def force_logout(user_id: int, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    admin_service.force_logout(db, admin_service.get_user(db, user_id), admin, ip_of(request))


@router.post("/admins", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_admin(data: AdminCreate, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = admin_service.create_admin(db, data.email, data.full_name, data.password, admin, ip_of(request))
    return UserOut.from_user(user)


@router.get("/system/health")
def system_health(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return admin_service.system_health(db)


# ---------- 37. moderation ----------

@router.get("/moderation/queue")
def moderation_queue(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return admin_service.moderation_queue(db)


@router.post("/hotels/{hotel_id}/suspend", response_model=HotelOut)
def suspend_hotel(hotel_id: int, data: HotelModeration, request: Request,
                  admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    hotel = hotel_service.get_hotel_or_404(db, hotel_id)
    return admin_service.change_hotel_status(db, hotel, HotelStatus.SUSPENDED.value, data.reason, admin, ip_of(request))


@router.post("/hotels/{hotel_id}/reinstate", response_model=HotelOut)
def reinstate_hotel(hotel_id: int, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    hotel = hotel_service.get_hotel_or_404(db, hotel_id)
    return admin_service.change_hotel_status(db, hotel, HotelStatus.APPROVED.value, None, admin, ip_of(request))


# ---------- 39. audit + security ----------

@router.get("/audit-logs", response_model=list[AuditLogOut])
def audit_logs(
    action: str | None = None, user_id: int | None = None, entity: str | None = None,
    days: int = Query(7, ge=1, le=365), limit: int = Query(100, ge=1, le=500),
    _: User = Depends(admin_only), db: Session = Depends(get_db),
):
    return audit_service.search(db, action, user_id, entity, days, limit)


@router.get("/security/overview")
def security_overview(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return audit_service.security_overview(
        db, settings_service.get_int(db, "max_failed_logins"), settings_service.get_int(db, "lockout_minutes")
    )


# ---------- 48. fraud ----------

@router.get("/fraud/flags", response_model=list[FraudFlagOut])
def fraud_flags(
    flag_status: Literal["OPEN", "CONFIRMED_FRAUD", "DISMISSED"] | None = "OPEN",
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(admin_only), db: Session = Depends(get_db),
):
    return fraud_service.list_flags(db, flag_status, limit)


@router.patch("/fraud/flags/{flag_id}", response_model=FraudFlagOut)
def review_flag(flag_id: int, data: FraudReview, request: Request,
                admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return fraud_service.review_flag(db, flag_id, data.status, data.note, admin, ip_of(request), data.block_user)


# ---------- 49. system configuration ----------

@router.get("/settings", response_model=list[SettingOut])
def all_settings(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return settings_service.list_all(db)


@router.put("/settings/{key}", response_model=SettingOut)
def change_setting(key: str, data: SettingUpdate, request: Request,
                   admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return settings_service.update(db, key, data.value, admin, ip_of(request))
