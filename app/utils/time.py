from datetime import datetime, timezone


def utcnow() -> datetime:
    # MySQL DATETIME has no timezone, so we store plain UTC times everywhere
    return datetime.now(timezone.utc).replace(tzinfo=None)