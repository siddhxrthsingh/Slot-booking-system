"""
Booking service: availability checks, create/cancel bookings, quota + policy enforcement.

Policy:
  - All bookings auto-confirmed (no manual approval flow).
  - 1 booking per sport per day per student.
  - No time-clash: a student cannot hold two bookings at the same time.
  - Cancellation must happen >= CANCEL_WINDOW_HOURS before slot start.
  - Late cancellation (< window) → apply a BAN_DURATION_DAYS ban.
  - Banned students cannot make new bookings until the ban expires.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings

settings = get_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot_start_dt(slot: dict) -> datetime:
    """Combine slot['date'] (datetime) and slot['start_time'] (HH:MM) into UTC datetime."""
    d: datetime = slot["date"]
    h, m = map(int, slot["start_time"].split(":"))
    return d.replace(hour=h, minute=m, second=0, microsecond=0, tzinfo=timezone.utc)


def _slot_end_dt(slot: dict) -> datetime:
    d: datetime = slot["date"]
    h, m = map(int, slot["end_time"].split(":"))
    return d.replace(hour=h, minute=m, second=0, microsecond=0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Ban helpers
# ---------------------------------------------------------------------------

async def check_user_ban(db: AsyncIOMotorDatabase, user_oid: ObjectId) -> dict | None:
    """Return active ban document if the user is currently banned, else None."""
    now = datetime.now(timezone.utc)
    return await db["bans"].find_one(
        {"user_id": user_oid, "banned_until": {"$gt": now}}
    )


async def apply_ban(db: AsyncIOMotorDatabase, user_oid: ObjectId, reason: str) -> None:
    """Create (or refresh) a ban record for the user."""
    now = datetime.now(timezone.utc)
    banned_until = now + timedelta(days=settings.ban_duration_days)
    await db["bans"].update_one(
        {"user_id": user_oid},
        {
            "$set": {
                "user_id":     user_oid,
                "reason":      reason,
                "banned_until": banned_until,
                "created_at":  now,
            }
        },
        upsert=True,
    )


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

async def list_available_slots(
    db: AsyncIOMotorDatabase,
    sport: str | None = None,
    date: datetime | None = None,
    campus: str | None = None,
    venue: str | None = None,
) -> list[dict]:
    query: dict = {"status": "open"}
    if sport:
        query["sport"] = {"$regex": sport, "$options": "i"}
    if campus:
        query["campus"] = campus
    if venue:
        query["venue"] = {"$regex": venue, "$options": "i"}
    if date:
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query["date"] = {"$gte": start, "$lte": end}

    slots = await db["slots"].find(query).sort("date", 1).to_list(length=200)
    return slots


# ---------------------------------------------------------------------------
# Create booking
# ---------------------------------------------------------------------------

async def create_booking(
    db: AsyncIOMotorDatabase,
    user_id: str,
    slot_id: str,
    notes: str | None = None,
) -> dict:
    slot_oid = ObjectId(slot_id)
    user_oid = ObjectId(user_id)
    now      = datetime.now(timezone.utc)

    # ── Ban check ────────────────────────────────────────────────────────────
    ban = await check_user_ban(db, user_oid)
    if ban:
        until = ban["banned_until"].strftime("%d %b %Y, %H:%M UTC")
        raise ValueError(f"Your booking access is suspended until {until}.")

    # ── Fetch slot ───────────────────────────────────────────────────────────
    slot = await db["slots"].find_one({"_id": slot_oid, "status": "open"})
    if not slot:
        raise LookupError("Slot not found or is not open.")

    slot_start = _slot_start_dt(slot)
    slot_end   = _slot_end_dt(slot)

    # ── Duplicate check ──────────────────────────────────────────────────────
    existing = await db["bookings"].find_one(
        {"user_id": user_oid, "slot_id": slot_oid, "status": {"$ne": "cancelled"}}
    )
    if existing:
        raise ValueError("You already have a booking for this slot.")

    # ── 1 booking per sport per day ──────────────────────────────────────────
    day_start = slot_start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = slot_start.replace(hour=23, minute=59, second=59)

    same_day_slots = await db["slots"].find(
        {"sport": slot["sport"], "date": {"$gte": day_start, "$lte": day_end}}
    ).to_list(length=100)
    same_day_slot_ids = [s["_id"] for s in same_day_slots]

    same_day_booking = await db["bookings"].find_one({
        "user_id": user_oid,
        "slot_id": {"$in": same_day_slot_ids},
        "status":  {"$nin": ["cancelled"]},
    })
    if same_day_booking:
        raise ValueError(
            f"You already have a {slot['sport']} booking on this day. "
            "Only 1 booking per sport per day is allowed."
        )

    # ── Time-clash check ─────────────────────────────────────────────────────
    # Find all non-cancelled bookings for this user, enrich with slot times
    active_bookings = await db["bookings"].find(
        {"user_id": user_oid, "status": {"$nin": ["cancelled"]}}
    ).to_list(length=200)

    for ab in active_bookings:
        ab_slot = await db["slots"].find_one({"_id": ab["slot_id"]})
        if not ab_slot:
            continue
        ab_start = _slot_start_dt(ab_slot)
        ab_end   = _slot_end_dt(ab_slot)
        # Overlap: [start, end) overlaps [ab_start, ab_end)
        if slot_start < ab_end and slot_end > ab_start:
            raise ValueError(
                f"Time clash with your existing {ab['sport']} booking "
                f"({ab_slot['start_time']}–{ab_slot['end_time']}). "
                "You cannot book two sports at the same time."
            )

    # ── Atomic seat reservation ──────────────────────────────────────────────
    updated_slot = await db["slots"].find_one_and_update(
        {
            "_id":    slot_oid,
            "status": "open",
            "$expr":  {"$lt": ["$booked_count", "$capacity"]},
        },
        {"$inc": {"booked_count": 1}},
        return_document=True,
    )
    if not updated_slot:
        raise ValueError("Slot is full or no longer available.")

    if updated_slot["booked_count"] >= updated_slot["capacity"]:
        await db["slots"].update_one({"_id": slot_oid}, {"$set": {"status": "full"}})

    # Auto-confirm all bookings
    booking_doc = {
        "user_id":      user_oid,
        "slot_id":      slot_oid,
        "sport":        slot["sport"],
        "status":       "confirmed",
        "booking_date": now,
        "cancelled_at": None,
        "notes":        notes,
        "approved_by":  None,
        "created_at":   now,
        "updated_at":   now,
    }

    result = await db["bookings"].insert_one(booking_doc)
    booking_doc["_id"] = result.inserted_id
    return booking_doc


# ---------------------------------------------------------------------------
# My bookings
# ---------------------------------------------------------------------------

async def get_user_bookings(
    db: AsyncIOMotorDatabase,
    user_id: str,
    status_filter: str | None = None,
) -> list[dict]:
    query: dict = {"user_id": ObjectId(user_id)}
    if status_filter:
        query["status"] = status_filter

    bookings = await db["bookings"].find(query).sort("created_at", -1).to_list(length=200)

    enriched = []
    for b in bookings:
        slot = await db["slots"].find_one({"_id": b["slot_id"]})
        entry = {
            "id":           str(b["_id"]),
            "slot_id":      str(b["slot_id"]),
            "sport":        b["sport"],
            "status":       b["status"],
            "booking_date": b["booking_date"],
            "cancelled_at": b.get("cancelled_at"),
            "notes":        b.get("notes"),
            "created_at":   b["created_at"],
        }
        if slot:
            entry.update({
                "slot_date":       slot.get("date"),
                "slot_start_time": slot.get("start_time"),
                "slot_end_time":   slot.get("end_time"),
                "slot_venue":      slot.get("venue"),
                "slot_campus":     slot.get("campus"),
            })
        enriched.append(entry)

    return enriched


# ---------------------------------------------------------------------------
# Cancel booking
# ---------------------------------------------------------------------------

async def cancel_booking(
    db: AsyncIOMotorDatabase,
    booking_id: str,
    user_id: str,
) -> dict:
    booking_oid = ObjectId(booking_id)
    user_oid    = ObjectId(user_id)

    booking = await db["bookings"].find_one({"_id": booking_oid, "user_id": user_oid})
    if not booking:
        raise LookupError("Booking not found.")
    if booking["status"] == "cancelled":
        raise ValueError("Booking is already cancelled.")

    slot = await db["slots"].find_one({"_id": booking["slot_id"]})
    now  = datetime.now(timezone.utc)

    late_cancel = False
    if slot:
        slot_start = _slot_start_dt(slot)
        hours_until = (slot_start - now).total_seconds() / 3600
        if hours_until < settings.cancel_window_hours:
            late_cancel = True
            # Apply ban for late cancellation
            await apply_ban(
                db,
                user_oid,
                f"Late cancellation of {slot['sport']} slot on "
                f"{slot_start.strftime('%d %b %Y %H:%M')} UTC.",
            )

    # Release the seat
    if slot:
        await db["slots"].update_one(
            {"_id": booking["slot_id"]},
            {"$inc": {"booked_count": -1}, "$set": {"status": "open"}},
        )

    updated = await db["bookings"].find_one_and_update(
        {"_id": booking_oid},
        {"$set": {
            "status":       "cancelled",
            "cancelled_at": now,
            "updated_at":   now,
            "late_cancel":  late_cancel,
        }},
        return_document=True,
    )
    return updated
