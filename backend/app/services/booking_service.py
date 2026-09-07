"""
Booking service: availability checks, join/cancel bookings, quota + policy enforcement.

Join policy (Phase 3 Step 1B):
  - Facility capacity is authoritative; capacity check/increment is atomic.
  - Multiple students may join the same slot (shared slots).
  - First active participant becomes the leader (leader_user_id / is_leader).
  - A user cannot hold two ACTIVE participations in the same slot.
  - A user who has previously left/cancelled a slot cannot rejoin it.
  - Maximum 2 ACTIVE slots per calendar day per student, across all sports/facilities.
  - Active bookings for the same student must not overlap in time.
  - Banned students cannot make new bookings until the ban expires.

Cancellation/leave behavior is out of scope for this step and remains as before.
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
    """End of the slot. Prefers start_time + duration_minutes (supports arbitrary-duration
    manual slots); falls back to end_time when duration_minutes is not set."""
    duration = slot.get("duration_minutes")
    if duration:
        return _slot_start_dt(slot) + timedelta(minutes=duration)
    d: datetime = slot["date"]
    h, m = map(int, slot["end_time"].split(":"))
    return d.replace(hour=h, minute=m, second=0, microsecond=0, tzinfo=timezone.utc)


def _build_user_snapshot(user: dict) -> dict:
    return {
        "name": user.get("name"),
        "srn": user.get("srn"),
        "phone": user.get("phone"),
        "branch": user.get("branch"),
        "program": user.get("program"),
        "semester": user.get("semester"),
        "section": user.get("section"),
        "campus": user.get("campus"),
    }


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

def serialize_student_slot(slot: dict) -> dict:
    facility_id = slot.get("facility_id")
    facility_name = slot.get("facility_name")
    capacity = slot.get("capacity", 0)
    booked_count = slot.get("booked_count", 0)
    return {
        "id": str(slot["_id"]),
        "facility_id": str(facility_id) if facility_id else None,
        "facility_name": facility_name,
        "sport": slot["sport"],
        "date": slot["date"],
        "start_time": slot["start_time"],
        "end_time": slot["end_time"],
        "venue": slot.get("venue") or facility_name or "",
        "campus": slot["campus"],
        "duration_minutes": slot.get("duration_minutes"),
        "capacity": capacity,
        "booked_count": booked_count,
        "available_count": max(capacity - booked_count, 0),
        "status": slot["status"],
        "slot_type": slot.get("slot_type"),
        "is_manual": slot.get("is_manual", False),
        "requires_approval": slot.get("requires_approval", False),
    }


async def list_available_slots(
    db: AsyncIOMotorDatabase,
    sport: str | None = None,
    date: datetime | None = None,
    campus: str | None = None,
    venue: str | None = None,
) -> list[dict]:
    query: dict = {"status": {"$in": ["open", "full"]}}
    if sport:
        query["sport"] = {"$regex": sport, "$options": "i"}
    if campus:
        query["campus"] = campus
    if venue:
        query["$or"] = [
            {"venue": {"$regex": venue, "$options": "i"}},
            {"facility_name": {"$regex": venue, "$options": "i"}},
        ]
    if date:
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query["date"] = {"$gte": start, "$lte": end}

    slots = await db["slots"].find(query).sort(
        [("date", 1), ("sport", 1), ("start_time", 1), ("facility_name", 1)]
    ).to_list(length=500)
    now = datetime.now(timezone.utc)
    return [s for s in slots if _slot_end_dt(s) >= now]


# ---------------------------------------------------------------------------
# Join slot (create participation record)
# ---------------------------------------------------------------------------

MAX_ACTIVE_SLOTS_PER_DAY = 2


async def create_booking(
    db: AsyncIOMotorDatabase,
    user: dict,
    slot_id: str,
    notes: str | None = None,
) -> dict:
    """Join a slot as a participant.

    `user` is the authenticated user document (must contain at least `_id`;
    name/srn/phone/branch/program/semester/section/campus are used for the
    historical user_snapshot).
    """
    slot_oid = ObjectId(slot_id)
    user_oid = ObjectId(str(user["_id"]))
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

    # ── Duplicate active participation / rejoin-after-leaving check ─────────
    prior = await db["bookings"].find_one({"user_id": user_oid, "slot_id": slot_oid})
    if prior:
        if prior["status"] != "cancelled":
            raise ValueError("You have already joined this slot.")
        raise ValueError("You have already left this slot and cannot rejoin it.")

    # ── Maximum 2 ACTIVE slots per calendar day (all sports/facilities) ─────
    day_start = slot_start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = slot_start.replace(hour=23, minute=59, second=59, microsecond=999999)

    same_day_slots = await db["slots"].find(
        {"date": {"$gte": day_start, "$lte": day_end}}
    ).to_list(length=500)
    same_day_slot_ids = [s["_id"] for s in same_day_slots]

    active_same_day_count = await db["bookings"].find({
        "user_id": user_oid,
        "slot_id": {"$in": same_day_slot_ids},
        "status":  {"$ne": "cancelled"},
    }).to_list(length=MAX_ACTIVE_SLOTS_PER_DAY + 1)
    if len(active_same_day_count) >= MAX_ACTIVE_SLOTS_PER_DAY:
        raise ValueError(
            f"You already have {MAX_ACTIVE_SLOTS_PER_DAY} active bookings on this day. "
            f"Maximum {MAX_ACTIVE_SLOTS_PER_DAY} active slots per day is allowed."
        )

    # ── Overlap check across all active bookings (any day/sport) ────────────
    active_bookings = await db["bookings"].find(
        {"user_id": user_oid, "status": {"$ne": "cancelled"}}
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
                "You cannot hold overlapping bookings."
            )

    # ── Facility capacity is authoritative ───────────────────────────────────
    capacity = slot["capacity"]
    if slot.get("facility_id"):
        facility = await db["facilities"].find_one({"_id": ObjectId(str(slot["facility_id"]))})
        if facility and facility.get("capacity") is not None:
            capacity = facility["capacity"]

    # ── Atomic seat reservation ──────────────────────────────────────────────
    updated_slot = await db["slots"].find_one_and_update(
        {
            "_id":    slot_oid,
            "status": "open",
            "$expr":  {"$lt": ["$booked_count", capacity]},
        },
        {"$inc": {"booked_count": 1}},
        return_document=True,
    )
    if not updated_slot:
        raise ValueError("Slot is full or no longer available.")

    if updated_slot["booked_count"] >= capacity:
        await db["slots"].update_one({"_id": slot_oid}, {"$set": {"status": "full"}})

    # ── Leader assignment: the request that atomically took booked_count from
    # 0 → 1 is the first successful participant, so it becomes leader. Since
    # the increment above is atomic and MongoDB serializes per-document
    # updates, `booked_count == 1` can be true for exactly one caller across
    # the whole system — no separate race-prone claim step is needed.
    is_leader = updated_slot["booked_count"] == 1
    if is_leader:
        await db["slots"].update_one(
            {"_id": slot_oid}, {"$set": {"leader_user_id": user_oid}}
        )

    # ── Create participation record ──────────────────────────────────────────
    booking_doc = {
        "user_id":      user_oid,
        "slot_id":      slot_oid,
        "facility_id":  ObjectId(str(slot["facility_id"])) if slot.get("facility_id") else None,
        "sport":        slot["sport"],
        "status":       "confirmed",
        "booking_date": now,
        "joined_at":    now,
        "cancelled_at": None,
        "cancelled_by": None,
        "is_leader":    is_leader,
        "user_snapshot": _build_user_snapshot(user),
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
# Cancel booking (leave a slot — per-participant, not a slot-wide cancellation)
# ---------------------------------------------------------------------------

async def cancel_booking(
    db: AsyncIOMotorDatabase,
    booking_id: str,
    user_id: str,
) -> dict:
    """A student leaves their own active participation in a slot.

    Only the leaving participant's booking record is affected — the shared
    slot and other participants' bookings are untouched beyond the capacity
    count and (if the leaver was leader) leader promotion. The booking record
    is never deleted; it is preserved with status="cancelled" for history.
    """
    booking_oid = ObjectId(booking_id)
    user_oid    = ObjectId(user_id)
    now         = datetime.now(timezone.utc)

    booking = await db["bookings"].find_one({"_id": booking_oid, "user_id": user_oid})
    if not booking:
        raise LookupError("Booking not found.")
    if booking["status"] == "cancelled":
        raise ValueError("Booking is already cancelled.")

    slot = await db["slots"].find_one({"_id": booking["slot_id"]})

    late_cancel = False
    if slot:
        slot_start = _slot_start_dt(slot)
        hours_until = (slot_start - now).total_seconds() / 3600
        late_cancel = hours_until < settings.cancel_window_hours

    # ── Atomic, idempotent status transition ─────────────────────────────────
    # Guarding on status != "cancelled" here (not just the earlier read) makes
    # this safe against duplicate/concurrent cancellation requests for the
    # same booking: only the caller that actually flips the status proceeds
    # to apply the ban / decrement the slot / promote a new leader.
    updated = await db["bookings"].find_one_and_update(
        {"_id": booking_oid, "user_id": user_oid, "status": {"$ne": "cancelled"}},
        {"$set": {
            "status":       "cancelled",
            "cancelled_at": now,
            "cancelled_by": user_oid,
            "updated_at":   now,
            "late_cancel":  late_cancel,
        }},
        return_document=True,
    )
    if not updated:
        raise ValueError("Booking is already cancelled.")

    if late_cancel and slot:
        slot_start = _slot_start_dt(slot)
        await apply_ban(
            db,
            user_oid,
            f"Late cancellation of {slot['sport']} slot on "
            f"{slot_start.strftime('%d %b %Y %H:%M')} UTC.",
        )

    if slot:
        # ── Atomic seat release, guarded against going negative ─────────────
        released_slot = await db["slots"].find_one_and_update(
            {"_id": slot["_id"], "booked_count": {"$gt": 0}},
            {"$inc": {"booked_count": -1}},
            return_document=True,
        )
        if released_slot:
            capacity = released_slot.get("capacity")
            if released_slot.get("facility_id"):
                facility = await db["facilities"].find_one(
                    {"_id": ObjectId(str(released_slot["facility_id"]))}
                )
                if facility and facility.get("capacity") is not None:
                    capacity = facility["capacity"]
            if released_slot.get("status") == "full" and released_slot["booked_count"] < capacity:
                await db["slots"].update_one({"_id": slot["_id"]}, {"$set": {"status": "open"}})

        # ── Leader promotion: earliest joined remaining active participant ──
        # The promotion write is guarded by status != "cancelled" so a
        # candidate who is concurrently leaving between selection and write
        # can never be promoted. If that guard fails (candidate cancelled in
        # the meantime), the remaining active participants are re-read and
        # the next earliest candidate is tried, until one is promoted or none
        # remain.
        if updated.get("is_leader"):
            new_leader_user_id = None
            excluded_ids = set()
            while True:
                remaining = await db["bookings"].find({
                    "slot_id": slot["_id"],
                    "status": {"$ne": "cancelled"},
                    "_id": {"$nin": list(excluded_ids)},
                }).sort("joined_at", 1).to_list(length=1)
                if not remaining:
                    break

                candidate = remaining[0]
                promoted = await db["bookings"].find_one_and_update(
                    {"_id": candidate["_id"], "status": {"$ne": "cancelled"}},
                    {"$set": {"is_leader": True}},
                    return_document=True,
                )
                if promoted:
                    new_leader_user_id = promoted["user_id"]
                    break

                # Candidate was cancelled concurrently — exclude and retry.
                excluded_ids.add(candidate["_id"])

            await db["slots"].update_one(
                {"_id": slot["_id"]}, {"$set": {"leader_user_id": new_leader_user_id}}
            )

    return updated
