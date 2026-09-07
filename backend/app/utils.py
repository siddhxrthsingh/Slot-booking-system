from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

# Sole business timezone: PES University RR Campus, India. Never derive
# "today"/expiry/display times from the server or viewer's local timezone.
IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to a naive datetime read back from MongoDB.

    Motor/PyMongo always stores instants as UTC but returns them as naive
    datetime objects. Passing a naive value straight to JSON serialization
    drops the timezone entirely, and browsers then parse the resulting
    string as *local* time instead of UTC (e.g. JS `new Date("...")` on an
    offset-less ISO string). Every point-in-time timestamp read from the DB
    (joined_at, cancelled_at, banned_until, ...) must go through this before
    being returned in an API response.
    """
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def success_response(data: Any, message: str = "Operation successful") -> dict:
    return {
        "status": True,
        "data": data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def error_response(error: str, message: str) -> dict:
    return {
        "status": False,
        "error": error,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
