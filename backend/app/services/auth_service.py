"""
Auth service: PESUAuth integration, admin login, JWT generation, session management.
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
# Admin (employee-ID) login — no external API required
# ---------------------------------------------------------------------------

def is_admin_employee_id(username: str) -> bool:
    """True when the username matches the configured admin employee ID."""
    return username.upper() == settings.admin_employee_id.upper()


async def verify_admin_credentials(username: str, password: str) -> dict | None:
    """
    Authenticate with local admin credentials (no PESUAuth call).
    Returns a profile dict on success, None on wrong password.
    """
    if not is_admin_employee_id(username):
        return None
    if password != settings.admin_password:
        return None
    return {
        "employee_id": settings.admin_employee_id.upper(),
        "name":        settings.admin_name,
        "email":       settings.admin_email,
        "role":        "admin",
    }


async def upsert_admin(db: AsyncIOMotorDatabase, profile: dict) -> dict:
    """Create or refresh the admin user document."""
    now = datetime.now(timezone.utc)
    eid = profile["employee_id"]

    result = await db["users"].find_one_and_update(
        {"srn": eid},
        {
            "$set": {
                "email":      profile.get("email", ""),
                "name":       profile.get("name", ""),
                "role":       "admin",
                "last_login": now,
            },
            "$setOnInsert": {
                "srn":        eid,
                "created_at": now,
            },
        },
        upsert=True,
        return_document=True,
    )
    return result


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
# PESUAuth integration  (https://github.com/pesu-dev/auth)
# Live endpoint: https://pesu-auth.onrender.com/authenticate
# ---------------------------------------------------------------------------

# campus_code returned by PESUAuth: 1 = RR, 2 = EC
_CAMPUS_CODE_MAP = {1: "RR", 2: "EC"}


async def verify_pesu_credentials(username: str, password: str) -> dict | None:
    """
    Call the live PESUAuth API to validate PESU Academy credentials.
    Returns a normalised profile dict on success, None on wrong credentials.
    Raises httpx.RequestError on network failure (router converts to 503).

    Accepts: SRN, PRN, email address, or registered phone number.
    """
    try:
        # Render free-tier can cold-start — use a generous timeout.
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(
                settings.pesu_auth_url,
                json={"username": username, "password": password, "profile": True},
            )

        # 401 = wrong credentials — return None so router sends 401 to browser.
        if response.status_code == 401:
            return None

        if response.status_code != 200:
            raise httpx.RequestError(
                f"PESUAuth returned unexpected status {response.status_code}"
            )

        data = response.json()
        if not data.get("status"):
            return None

        raw = data.get("profile") or {}

        # campus field is "RR"/"EC" string; fall back to campus_code int if missing.
        campus = raw.get("campus") or _CAMPUS_CODE_MAP.get(raw.get("campus_code"))

        return {
            "srn":      raw.get("srn") or raw.get("prn") or username.upper(),
            "name":     raw.get("name", ""),
            "email":    raw.get("email", ""),
            "program":  raw.get("program"),
            "branch":   raw.get("branch"),
            "campus":   campus,
            "semester": raw.get("semester"),
            "section":  raw.get("section"),
        }

    except httpx.RequestError:
        # Dev-only bypass: lets you test locally without hitting the real API.
        # Disabled automatically when APP_ENV=production.
        if settings.app_env == "development":
            return _mock_pesu_profile(username)
        raise


def _mock_pesu_profile(username: str) -> dict:
    """Development-only mock. Never active when APP_ENV=production."""
    return {
        "srn":      username.upper(),
        "email":    f"{username.lower()}@pesu.pes.edu",
        "name":     "Dev User (mock)",
        "program":  "Bachelor of Technology",
        "branch":   "Computer Science and Engineering",
        "campus":   "RR",
        "semester": "6",
        "section":  "A",
    }


# ---------------------------------------------------------------------------
# User upsert
# ---------------------------------------------------------------------------

async def upsert_user(db: AsyncIOMotorDatabase, profile: dict) -> dict:
    """Create a new user record or refresh last_login for a returning user."""
    now = datetime.now(timezone.utc)
    srn = (profile.get("srn") or "").upper()
    if not srn:
        raise ValueError("PESUAuth did not return an SRN for this user.")

    result = await db["users"].find_one_and_update(
        {"srn": srn},
        {
            "$set": {
                "email":      profile.get("email", ""),
                "name":       profile.get("name", ""),
                "program":    profile.get("program"),
                "branch":     profile.get("branch"),
                "campus":     profile.get("campus"),
                "semester":   profile.get("semester"),
                "section":    profile.get("section"),
                "last_login": now,
            },
            "$setOnInsert": {
                "srn":        srn,
                "role":       "student",
                "created_at": now,
            },
        },
        upsert=True,
        return_document=True,
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
