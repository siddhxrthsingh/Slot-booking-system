"""
Booking service: availability checks, create/cancel bookings, quota enforcement.
"""
from datetime import datetime, timezone
from typing import Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.booking import BookingWithSlot

# Students can hold at most this many active bookings at a time
MAX_ACTIVE_BOOKINGS = 3


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
        # Match all slots on the given calendar day
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query["date"] = {"$gte": start, "$lte": end}

    slots = await db["slots"].find(query).sort("date", 1).to_list(length=200)
    return slots


# ---------------------------------------------------------------------------
# Create booking (atomic increment to prevent overbooking)
# ---------------------------------------------------------------------------

async def create_booking(
    db: AsyncIOMotorDatabase,
    user_id: str,
    slot_id: str,
    notes: str | None = None,
) -> dict:
    slot_oid = ObjectId(slot_id)
    user_oid = ObjectId(user_id)

    # --- Quota check ---
    active_count = await db["bookings"].count_documents(
        {"user_id": user_oid, "status": {"$in": ["confirmed", "pending_approval"]}}
    )
    if active_count >= MAX_ACTIVE_BOOKINGS:
        raise ValueError(f"Booking limit reached. Maximum {MAX_ACTIVE_BOOKINGS} active bookings allowed.")

    # --- Duplicate check ---
    existing = await db["bookings"].find_one(
        {"user_id": user_oid, "slot_id": slot_oid, "status": {"$ne": "cancelled"}}
    )
    if existing:
        raise ValueError("You already have a booking for this slot.")

    # --- Atomic availability increment ---
    slot = await db["slots"].find_one_and_update(
        {
            "_id": slot_oid,
            "status": "open",
            "$expr": {"$lt": ["$booked_count", "$capacity"]},
        },
        {"$inc": {"booked_count": 1}},
        return_document=True,
    )
    if not slot:
        raise ValueError("Slot is not available or is already full.")

    # If slot is now full, mark it
    if slot["booked_count"] >= slot["capacity"]:
        await db["slots"].update_one({"_id": slot_oid}, {"$set": {"status": "full"}})

    # Determine booking status
    booking_status: Literal["confirmed", "pending_approval"] = (
        "pending_approval" if slot.get("requires_approval") else "confirmed"
    )

    now = datetime.now(timezone.utc)
    booking_doc = {
        "user_id": user_oid,
        "slot_id": slot_oid,
        "sport": slot["sport"],
        "status": booking_status,
        "booking_date": now,
        "cancelled_at": None,
        "notes": notes,
        "approved_by": None,
        "created_at": now,
        "updated_at": now,
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

    # Enrich with slot details
    enriched = []
    for b in bookings:
        slot = await db["slots"].find_one({"_id": b["slot_id"]})
        entry = {
            "id": str(b["_id"]),
            "slot_id": str(b["slot_id"]),
            "sport": b["sport"],
            "status": b["status"],
            "booking_date": b["booking_date"],
            "cancelled_at": b.get("cancelled_at"),
            "notes": b.get("notes"),
            "created_at": b["created_at"],
        }
        if slot:
            entry.update(
                {
                    "slot_date": slot.get("date"),
                    "slot_start_time": slot.get("start_time"),
                    "slot_end_time": slot.get("end_time"),
                    "slot_venue": slot.get("venue"),
                    "slot_campus": slot.get("campus"),
                }
            )
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
    user_oid = ObjectId(user_id)

    booking = await db["bookings"].find_one({"_id": booking_oid, "user_id": user_oid})
    if not booking:
        raise LookupError("Booking not found.")
    if booking["status"] == "cancelled":
        raise ValueError("Booking is already cancelled.")

    now = datetime.now(timezone.utc)

    # Release the seat back to the slot
    await db["slots"].update_one(
        {"_id": booking["slot_id"]},
        {
            "$inc": {"booked_count": -1},
            "$set": {"status": "open"},
        },
    )

    updated = await db["bookings"].find_one_and_update(
        {"_id": booking_oid},
        {"$set": {"status": "cancelled", "cancelled_at": now, "updated_at": now}},
        return_document=True,
    )
    return updated
