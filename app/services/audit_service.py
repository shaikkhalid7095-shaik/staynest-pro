from datetime import timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, LoginAttempt
from app.utils.time import utcnow


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # behind a proxy the real address is in X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def log(db: Session, user_id: int | None, action: str, entity: str | None = None,
        entity_id: int | None = None, details: str | None = None, ip: str | None = None):
    # added to the session only - the caller commits with its own change
    db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id, details=details, ip_address=ip))


def search(db: Session, action: str | None, user_id: int | None, entity: str | None, days: int, limit: int):
    query = select(AuditLog).where(AuditLog.created_at >= utcnow() - timedelta(days=days))
    if action:
        query = query.where(AuditLog.action == action.upper())
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if entity:
        query = query.where(AuditLog.entity == entity)
    return list(db.scalars(query.order_by(AuditLog.id.desc()).limit(limit)))


def recent_failures(db: Session, email: str, minutes: int) -> int:
    since = utcnow() - timedelta(minutes=minutes)
    return db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.email == email, LoginAttempt.success.is_(False), LoginAttempt.created_at >= since
        )
    ) or 0


def security_overview(db: Session, max_failed: int, lockout_minutes: int) -> dict:
    day_ago = utcnow() - timedelta(hours=24)
    failed_24h = db.scalar(
        select(func.count(LoginAttempt.id)).where(LoginAttempt.success.is_(False), LoginAttempt.created_at >= day_ago)
    ) or 0
    success_24h = db.scalar(
        select(func.count(LoginAttempt.id)).where(LoginAttempt.success.is_(True), LoginAttempt.created_at >= day_ago)
    ) or 0

    rows = db.execute(
        select(LoginAttempt.email, func.count(LoginAttempt.id))
        .where(LoginAttempt.success.is_(False), LoginAttempt.created_at >= day_ago)
        .group_by(LoginAttempt.email)
        .order_by(func.count(LoginAttempt.id).desc())
        .limit(10)
    ).all()
    ip_rows = db.execute(
        select(LoginAttempt.ip_address, func.count(LoginAttempt.id))
        .where(LoginAttempt.success.is_(False), LoginAttempt.created_at >= day_ago)
        .group_by(LoginAttempt.ip_address)
        .order_by(func.count(LoginAttempt.id).desc())
        .limit(10)
    ).all()

    locked = [email for email, _ in rows if recent_failures(db, email, lockout_minutes) >= max_failed]
    return {
        "failed_logins_24h": failed_24h,
        "successful_logins_24h": success_24h,
        "top_failed_emails": [{"email": e, "failures": n} for e, n in rows],
        "top_failed_ips": [{"ip": ip or "unknown", "failures": n} for ip, n in ip_rows],
        "locked_emails": locked,
    }
