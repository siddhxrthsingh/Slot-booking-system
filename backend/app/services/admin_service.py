"""
Admin service: slot management, booking approvals, metrics.
"""
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.booking_service import _slot_end_dt


def _filter_active_slots(slots: list[dict], now: datetime | None = None) -> list[dict]:
    """Keep open/full slots whose end time has not passed."""
    now = now or datetime.now(timezone.utc)
    return [
        s for s in slots
        if s.get("status") in ("open", "full") and _slot_end_dt(s) >= now
    ]


# ---------------------------------------------------------------------------
# Slot management
# ---------------------------------------------------------------------------

async def list_all_slots(
    db: AsyncIOMotorDatabase,
    campus: str | None = None,
    sport: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    query: dict = {}
    if active_only:
        query["status"] = {"$in": ["open", "full"]}
    if campus:
        query["campus"] = campus
    if sport:
        query["sport"] = {"$regex": sport, "$options": "i"}

    slots = await db["slots"].find(query).sort("date", 1).to_list(length=500)
    if active_only:
        slots = _filter_active_slots(slots)
    return slots


async def create_slot(db: AsyncIOMotorDatabase, slot_data: dict, admin_id: str) -> dict:
    slot_data["created_by"] = ObjectId(admin_id)
    slot_data["created_at"] = datetime.now(timezone.utc)
    slot_data["booked_count"] = 0
    slot_data["status"] = "open"
    result = await db["slots"].insert_one(slot_data)
    slot_data["_id"] = result.inserted_id
    return slot_data


async def update_slot(
    db: AsyncIOMotorDatabase, slot_id: str, updates: dict
) -> dict | None:
    updates["updated_at"] = datetime.now(timezone.utc)
    updated = await db["slots"].find_one_and_update(
        {"_id": ObjectId(slot_id)},
        {"$set": updates},
        return_document=True,
    )
    return updated


async def cancel_slot(db: AsyncIOMotorDatabase, slot_id: str) -> int:
    """Cancel a slot and cascade-cancel all non-cancelled bookings."""
    slot_oid = ObjectId(slot_id)
    await db["slots"].update_one({"_id": slot_oid}, {"$set": {"status": "cancelled"}})

    now = datetime.now(timezone.utc)
    result = await db["bookings"].update_many(
        {"slot_id": slot_oid, "status": {"$ne": "cancelled"}},
        {"$set": {"status": "cancelled", "cancelled_at": now, "updated_at": now}},
    )
    return result.modified_count


# ---------------------------------------------------------------------------
# Booking approvals
# ---------------------------------------------------------------------------

async def list_pending_bookings(db: AsyncIOMotorDatabase) -> list[dict]:
    bookings = (
        await db["bookings"]
        .find({"status": "pending_approval"})
        .sort("created_at", 1)
        .to_list(length=200)
    )
    enriched = []
    for b in bookings:
        user = await db["users"].find_one({"_id": b["user_id"]}, {"password": 0})
        slot = await db["slots"].find_one({"_id": b["slot_id"]})
        enriched.append(
            {
                "id": str(b["_id"]),
                "slot_id": str(b["slot_id"]),
                "sport": b["sport"],
                "status": b["status"],
                "booking_date": b["booking_date"],
                "notes": b.get("notes"),
                "user": {
                    "id": str(user["_id"]),
                    "name": user.get("name"),
                    "srn": user.get("srn"),
                    "email": user.get("email"),
                }
                if user
                else None,
                "slot": {
                    "date": slot.get("date"),
                    "start_time": slot.get("start_time"),
                    "end_time": slot.get("end_time"),
                    "venue": slot.get("venue"),
                    "campus": slot.get("campus"),
                }
                if slot
                else None,
            }
        )
    return enriched


async def process_approval(
    db: AsyncIOMotorDatabase,
    booking_id: str,
    action: str,  # "approve" | "reject"
    admin_id: str,
    notes: str | None = None,
) -> dict | None:
    new_status = "confirmed" if action == "approve" else "cancelled"
    now = datetime.now(timezone.utc)

    update: dict = {
        "status": new_status,
        "updated_at": now,
        "approved_by": ObjectId(admin_id),
    }
    if notes:
        update["notes"] = notes
    if new_status == "cancelled":
        update["cancelled_at"] = now

    updated = await db["bookings"].find_one_and_update(
        {"_id": ObjectId(booking_id), "status": "pending_approval"},
        {"$set": update},
        return_document=True,
    )

    # If rejected, release the seat
    if updated and new_status == "cancelled":
        await db["slots"].update_one(
            {"_id": updated["slot_id"]},
            {"$inc": {"booked_count": -1}, "$set": {"status": "open"}},
        )

    return updated


# ---------------------------------------------------------------------------
# Metrics / dashboard
# ---------------------------------------------------------------------------

async def get_metrics(db: AsyncIOMotorDatabase) -> dict:
    total_slots = await db["slots"].count_documents({})
    open_full_slots = (
        await db["slots"]
        .find({"status": {"$in": ["open", "full"]}})
        .to_list(length=500)
    )
    active_slots = _filter_active_slots(open_full_slots)
    open_slots = sum(1 for s in active_slots if s["status"] == "open")
    full_slots = sum(1 for s in active_slots if s["status"] == "full")
    cancelled_slots = await db["slots"].count_documents({"status": "cancelled"})
    total_bookings = await db["bookings"].count_documents({})
    confirmed_bookings = await db["bookings"].count_documents({"status": "confirmed"})
    pending_bookings = await db["bookings"].count_documents({"status": "pending_approval"})
    cancelled_bookings = await db["bookings"].count_documents({"status": "cancelled"})
    total_users = await db["users"].count_documents({})

    total_capacity = sum(s["capacity"] for s in active_slots)
    total_booked = sum(s["booked_count"] for s in active_slots)
    occupancy_pct = 0.0
    if total_capacity > 0:
        occupancy_pct = round(total_booked / total_capacity * 100, 1)

    return {
        "slots": {
            "total": total_slots,
            "open": open_slots,
            "full": full_slots,
            "active": len(active_slots),
            "cancelled": cancelled_slots,
        },
        "bookings": {
            "total": total_bookings,
            "confirmed": confirmed_bookings,
            "pending_approval": pending_bookings,
            "cancelled": cancelled_bookings,
        },
        "users": {"total": total_users},
        "occupancy_pct": occupancy_pct,
    }


async def list_all_bookings(
    db: AsyncIOMotorDatabase,
    status_filter: str | None = None,
) -> list[dict]:
    query: dict = {}
    if status_filter:
        query["status"] = status_filter

    bookings = (
        await db["bookings"].find(query).sort("created_at", -1).to_list(length=500)
    )
    enriched = []
    for b in bookings:
        user = await db["users"].find_one({"_id": b["user_id"]}, {"password": 0})
        slot = await db["slots"].find_one({"_id": b["slot_id"]})
        enriched.append(
            {
                "id": str(b["_id"]),
                "slot_id": str(b["slot_id"]),
                "sport": b["sport"],
                "status": b["status"],
                "booking_date": b["booking_date"],
                "cancelled_at": b.get("cancelled_at"),
                "notes": b.get("notes"),
                "created_at": b["created_at"],
                "user": {
                    "id": str(user["_id"]),
                    "name": user.get("name"),
                    "srn": user.get("srn"),
                    "email": user.get("email"),
                }
                if user
                else None,
                "slot": {
                    "date": slot.get("date"),
                    "start_time": slot.get("start_time"),
                    "end_time": slot.get("end_time"),
                    "venue": slot.get("venue"),
                    "campus": slot.get("campus"),
                }
                if slot
                else None,
            }
        )
    return enriched


# ---------------------------------------------------------------------------
# Facility inventory (read-only)
# ---------------------------------------------------------------------------

async def list_facilities(db: AsyncIOMotorDatabase, campus: str = "RR") -> list[dict]:
    """Return the facility inventory for a campus, active and inactive alike.

    Ordering is deterministic: sort_order ascending, then name ascending —
    the same key used by seed_facilities.py's own verification query.
    """
    facilities = (
        await db["facilities"]
        .find({"campus": campus})
        .sort([("sort_order", 1), ("name", 1)])
        .to_list(length=200)
    )
    return [
        {
            "id":            str(f["_id"]),
            "campus":        f["campus"],
            "sport":         f["sport"],
            "facility_type": f["facility_type"],
            "name":          f["name"],
            "display_name":  f["display_name"],
            "capacity":      f["capacity"],
            "is_active":     f.get("is_active", True),
            "sort_order":    f.get("sort_order", 0),
        }
        for f in facilities
    ]


# ---------------------------------------------------------------------------
# Slot roster / accountability (read-only, admin-only)
# ---------------------------------------------------------------------------

async def get_slot_roster(db: AsyncIOMotorDatabase, slot_id: str) -> dict:
    """Return a slot's identity plus its full participation history.

    Includes active AND cancelled bookings (history is preserved, never
    deleted). Participant identity comes entirely from each booking's own
    stored `user_snapshot` — the live `users` collection is never queried
    here, since the snapshot is the historically-accurate accountability
    record for that participation.
    """
    try:
        slot_oid = ObjectId(slot_id)
    except InvalidId as e:
        # Normalize to ValueError, matching the ValueError -> 400 convention
        # already used by the student booking router (routers/bookings.py).
        raise ValueError(str(e)) from e

    slot = await db["slots"].find_one({"_id": slot_oid})
    if not slot:
        raise LookupError("Slot not found.")

    bookings = (
        await db["bookings"]
        .find({"slot_id": slot_oid})
        .sort("joined_at", 1)
        .to_list(length=500)
    )

    participants = [
        {
            "booking_id":    str(b["_id"]),
            "user_id":       str(b["user_id"]),
            "status":        b["status"],
            "is_leader":     b.get("is_leader", False),
            "joined_at":     b.get("joined_at"),
            "cancelled_at":  b.get("cancelled_at"),
            "cancelled_by":  str(b["cancelled_by"]) if b.get("cancelled_by") else None,
            "user_snapshot": b.get("user_snapshot"),
        }
        for b in bookings
    ]

    return {
        "slot": {
            "id":            str(slot["_id"]),
            "facility_id":   str(slot["facility_id"]) if slot.get("facility_id") else None,
            "facility_name": slot.get("facility_name"),
            "sport":         slot["sport"],
            "date":          slot["date"],
            "start_time":    slot["start_time"],
            "end_time":      slot["end_time"],
            "campus":        slot["campus"],
            "capacity":      slot["capacity"],
            "booked_count":  slot["booked_count"],
            "status":        slot["status"],
            "leader_user_id": str(slot["leader_user_id"]) if slot.get("leader_user_id") else None,
        },
        "participants": participants,
    }
