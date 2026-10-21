from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemSetting, User
from app.services import audit_service

# key: (default value, type, description, visible to everyone?)
DEFAULTS = {
    "platform_name": ("StayNest Pro", "str", "Name shown to users", True),
    "support_email": ("support@staynest.com", "str", "Where guests can write for help", True),
    "platform_commission_percent": ("10", "decimal", "Platform cut of each room booking", False),
    "loyalty_points_per_100": ("1", "int", "Points a guest earns per Rs 100 spent on rooms", True),
    "loyalty_rupees_per_point": ("1", "decimal", "Value of one point when redeemed", True),
    "max_failed_logins": ("5", "int", "Wrong passwords before an email is locked", False),
    "lockout_minutes": ("15", "int", "How long a locked email has to wait", False),
    "fraud_max_bookings_per_hour": ("3", "int", "More bookings than this in an hour gets flagged", False),
}


def get(db: Session, key: str) -> str:
    row = db.get(SystemSetting, key)
    return row.value if row else DEFAULTS[key][0]


def get_int(db: Session, key: str) -> int:
    return int(get(db, key))


def get_decimal(db: Session, key: str) -> Decimal:
    return Decimal(get(db, key))


def list_all(db: Session, public_only: bool = False) -> list[dict]:
    stored = {row.key: row for row in db.scalars(select(SystemSetting))}
    result = []
    for key, (default, kind, description, public) in DEFAULTS.items():
        if public_only and not public:
            continue
        row = stored.get(key)
        result.append({
            "key": key,
            "value": row.value if row else default,
            "default": default,
            "type": kind,
            "description": description,
            "is_public": public,
            "updated_at": row.updated_at if row else None,
        })
    return result


def _check_value(kind: str, value: str):
    try:
        if kind == "int" and int(value) < 0:
            raise ValueError
        if kind == "decimal" and Decimal(value) < 0:
            raise ValueError
    except (ValueError, InvalidOperation):
        raise HTTPException(422, f"Value must be a positive {kind}")


def update(db: Session, key: str, value: str, admin: User, ip: str | None) -> dict:
    if key not in DEFAULTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown setting '{key}'")
    value = value.strip()
    _check_value(DEFAULTS[key][1], value)

    old = get(db, key)
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=value)
        db.add(row)
    row.value = value
    row.updated_by_id = admin.id
    audit_service.log(db, admin.id, "SETTING_CHANGED", "setting", None, f"{key}: {old} -> {value}", ip)
    db.commit()
    return next(s for s in list_all(db) if s["key"] == key)
