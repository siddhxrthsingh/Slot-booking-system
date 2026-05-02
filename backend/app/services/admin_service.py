"""
Admin service: slot management, booking approvals, metrics.
"""
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


# ---------------------------------------------------------------------------
# Slot management
# ---------------------------------------------------------------------------

async def list_all_slots(
    db: AsyncIOMotorDatabase,
    campus: str | None = None,
    sport: str | None = None,
) -> list[dict]:
    query: dict = {}
    if campus:
        query["campus"] = campus
    if sport:
        query["sport"] = {"$regex": sport, "$options": "i"}

    slots = await db["slots"].find(query).sort("date", -1).to_list(length=500)
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
    open_slots = await db["slots"].count_documents({"status": "open"})
    full_slots = await db["slots"].count_documents({"status": "full"})
    cancelled_slots = await db["slots"].count_documents({"status": "cancelled"})
    total_bookings = await db["bookings"].count_documents({})
    confirmed_bookings = await db["bookings"].count_documents({"status": "confirmed"})
    pending_bookings = await db["bookings"].count_documents({"status": "pending_approval"})
    cancelled_bookings = await db["bookings"].count_documents({"status": "cancelled"})
    total_users = await db["users"].count_documents({})

    # Overall occupancy rate across open+full slots
    pipeline = [
        {"$match": {"status": {"$in": ["open", "full"]}}},
        {
            "$group": {
                "_id": None,
                "total_capacity": {"$sum": "$capacity"},
                "total_booked": {"$sum": "$booked_count"},
            }
        },
    ]
    agg = await db["slots"].aggregate(pipeline).to_list(length=1)
    occupancy_pct = 0.0
    if agg and agg[0]["total_capacity"] > 0:
        occupancy_pct = round(agg[0]["total_booked"] / agg[0]["total_capacity"] * 100, 1)

    return {
        "slots": {
            "total": total_slots,
            "open": open_slots,
            "full": full_slots,
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
