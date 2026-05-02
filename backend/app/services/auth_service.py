"""
Auth service: PESUAuth integration, JWT generation, session management.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId
from jose import jwt
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings

settings = get_settings()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_access_token(user_id: str, role: str) -> str:
    return _create_token(
        {"sub": user_id, "role": role, "type": "access"},
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str) -> str:
    """Return a plain refresh token (opaque random string)."""
    return secrets.token_urlsafe(64)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# PESUAuth integration
# ---------------------------------------------------------------------------

async def verify_pesu_credentials(username: str, password: str) -> dict | None:
    """
    Call the PESUAuth API to validate student credentials.
    Returns a profile dict on success, None on failure.

    If PESU_AUTH_URL is not reachable (e.g., local dev), this function
    raises an exception which the router handles.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                settings.pesu_auth_url,
                json={"username": username, "password": password},
            )
        if response.status_code != 200:
            return None
        data = response.json()
        # PESUAuth is expected to return a profile on success
        return data if data.get("status") else None
    except httpx.RequestError:
        # In development mode allow a mock bypass
        if settings.app_env == "development":
            return _mock_pesu_profile(username)
        raise


def _mock_pesu_profile(username: str) -> dict:
    """
    Mock profile returned in development when PESUAuth API is unavailable.
    Remove or gate this in production.
    """
    return {
        "status": True,
        "srn": username.upper(),
        "email": f"{username.lower()}@pesu.ac.in",
        "name": "Dev User",
        "program": "B.Tech",
        "branch": "CSE",
        "campus": "RR",
    }


# ---------------------------------------------------------------------------
# User upsert
# ---------------------------------------------------------------------------

async def upsert_user(db: AsyncIOMotorDatabase, profile: dict) -> dict:
    """Create a new user or update last_login for an existing one."""
    now = datetime.now(timezone.utc)
    srn = profile["srn"].upper()

    result = await db["users"].find_one_and_update(
        {"srn": srn},
        {
            "$set": {
                "email": profile.get("email", ""),
                "name": profile.get("name", ""),
                "program": profile.get("program"),
                "branch": profile.get("branch"),
                "campus": profile.get("campus"),
                "last_login": now,
            },
            "$setOnInsert": {
                "srn": srn,
                "role": "student",
                "created_at": now,
            },
        },
        upsert=True,
        return_document=True,  # return the updated/inserted document
    )
    return result


# ---------------------------------------------------------------------------
# Session management (refresh tokens)
# ---------------------------------------------------------------------------

async def create_session(
    db: AsyncIOMotorDatabase,
    user_id: str,
    refresh_token: str,
    ip_address: str | None = None,
) -> None:
    """Persist hashed refresh token in the sessions collection."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    await db["sessions"].insert_one(
        {
            "user_id": ObjectId(user_id),
            "refresh_token_hash": _hash_token(refresh_token),
            "expires_at": expires_at,
            "ip_address": ip_address,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def validate_refresh_token(
    db: AsyncIOMotorDatabase,
    refresh_token: str,
) -> dict | None:
    """Return the session document if valid, else None."""
    token_hash = _hash_token(refresh_token)
    session = await db["sessions"].find_one({"refresh_token_hash": token_hash})
    if not session:
        return None
    if session["expires_at"] < datetime.now(timezone.utc):
        await db["sessions"].delete_one({"_id": session["_id"]})
        return None
    return session


async def delete_session(db: AsyncIOMotorDatabase, refresh_token: str) -> None:
    token_hash = _hash_token(refresh_token)
    await db["sessions"].delete_one({"refresh_token_hash": token_hash})


async def delete_all_user_sessions(db: AsyncIOMotorDatabase, user_id: str) -> None:
    await db["sessions"].delete_many({"user_id": ObjectId(user_id)})
