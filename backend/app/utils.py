from datetime import datetime, timezone
from typing import Any


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
