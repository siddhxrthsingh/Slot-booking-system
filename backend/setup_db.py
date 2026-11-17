"""
Run once to create MongoDB indexes for the slot booking system.
Usage:  python setup_db.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from app.config import get_settings

ACTIVE_BOOKING_STATUSES = ["confirmed", "pending_approval"]
_FAILED_INDEXES: list[tuple[str, str]] = []
# IndexOptionsConflict / IndexKeySpecsConflict: an index with these keys or
# this name already exists with different options. We never drop it.
_CONFLICT_CODES = {85, 86}


def _is_index_conflict(exc: OperationFailure) -> bool:
    return exc.code in _CONFLICT_CODES


async def _ensure_index(collection, keys, **kwargs):
    """Create an index; on failure record it and continue (never drops)."""
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as exc:
        _FAILED_INDEXES.append((f"{collection.name}{keys}", str(exc)))
        print(f"  ! FAILED index on {collection.name} {keys}: {exc}")


async def main():
    _FAILED_INDEXES.clear()
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]

    print(f"Connected to MongoDB database: {settings.mongo_db_name}")

    # Users
    await db["users"].create_index("srn", unique=True)
    await db["users"].create_index("email")
    print("  ✓ users indexes")

    # Facilities
    await db["facilities"].create_index([("campus", 1), ("sport", 1), ("sort_order", 1)])
    # Facility identity (campus + sport + name) is relied on by seed_facilities.py
    # for idempotent upserts — enforce it as unique to prevent duplicate facility
    # documents from a bad upsert or manual insert.
    await db["facilities"].create_index(
        [("campus", 1), ("sport", 1), ("name", 1)], unique=True
    )
    print("  facilities indexes")

    # Schedule templates
    await db["schedule_templates"].create_index(
        [("campus", 1), ("sport", 1), ("day_type", 1), ("is_active", 1)]
    )
    await db["schedule_templates"].create_index(
        [("facility_id", 1), ("day_type", 1), ("is_active", 1)]
    )
    print("  schedule templates indexes")

    # Slots
    await db["slots"].create_index([("sport", 1), ("date", 1)])
    await db["slots"].create_index([("campus", 1), ("status", 1)])
    await db["slots"].create_index("date")
    await db["slots"].create_index([("facility_id", 1), ("date", 1)])
    await db["slots"].create_index([("facility_id", 1), ("date", 1), ("start_time", 1)])
    await db["slots"].create_index([("campus", 1), ("sport", 1), ("date", 1)])
    await db["slots"].create_index([("campus", 1), ("status", 1), ("date", 1)])
    await db["slots"].create_index(
        [
            ("campus", 1),
            ("facility_id", 1),
            ("date", 1),
            ("start_time", 1),
            ("end_time", 1),
            ("slot_type", 1),
        ],
        unique=True,
        partialFilterExpression={
            "slot_type": "generated",
            "facility_id": {"$type": "objectId"},
        },
    )
    print("  ✓ slots indexes")

    # Bookings
    # Index creation here is NON-DESTRUCTIVE: nothing is dropped, and a failure
    # of one index is reported but does not stop the remaining indexes.
    #
    # 1) Pilot policy: ONE active booking per student per calendar day, across
    #    all sports/facilities. `active_day_key` ("<user_id>:<YYYY-MM-DD>") is
    #    set on join and $unset on cancellation, so this partial unique index
    #    makes the rule atomic. Legacy bookings lack the field (excluded from
    #    the index) and are covered by the service-layer pre-check.
    #    Created FIRST so no earlier failure can prevent it.
    await _ensure_index(
        db["bookings"],
        "active_day_key",
        unique=True,
        partialFilterExpression={"active_day_key": {"$type": "string"}},
    )
    # 2) At most one ACTIVE booking document per user per slot. Partial filters
    #    do NOT support $ne (the old definition here was rejected by MongoDB and
    #    aborted setup). Statuses are confirmed | pending_approval | cancelled,
    #    so "active" == the first two. `$in` in a partial filter needs
    #    MongoDB >= 6.0; on older servers fall back to `$gt: "cancelled"`,
    #    which is supported everywhere and selects exactly those two values.
    #    Cancelled bookings stay exempt so early-cancel + rejoin still works
    #    and cancelled history is preserved.
    try:
        await db["bookings"].create_index(
            [("user_id", 1), ("slot_id", 1)],
            unique=True,
            partialFilterExpression={"status": {"$in": ACTIVE_BOOKING_STATUSES}},
        )
    except OperationFailure as exc:
        if _is_index_conflict(exc):
            _FAILED_INDEXES.append(("bookings(user_id,slot_id)", str(exc)))
        else:
            await _ensure_index(
                db["bookings"],
                [("user_id", 1), ("slot_id", 1)],
                unique=True,
                partialFilterExpression={"status": {"$gt": "cancelled"}},
            )
    await db["bookings"].create_index([("user_id", 1), ("status", 1)])
    await db["bookings"].create_index([("slot_id", 1), ("status", 1)])
    await db["bookings"].create_index("status")
    await db["bookings"].create_index([("facility_id", 1), ("status", 1)])
    print("  ✓ bookings indexes")

    # Sessions
    await db["sessions"].create_index("refresh_token_hash", unique=True)
    await db["sessions"].create_index("expires_at", expireAfterSeconds=0)
    print("  ✓ sessions indexes (TTL on expires_at)")

    # Bans
    # check_user_ban() (hit on every join attempt) filters on
    # {user_id, banned_until: {$gt: now}}; apply_ban()'s upsert and
    # unban_user()'s delete both filter on {user_id} alone. A single
    # compound index serves all three — bans had no index at all before.
    await db["bans"].create_index([("user_id", 1), ("banned_until", 1)])
    print("  ✓ bans indexes")

    client.close()
    print("\nAll indexes created successfully!")


if __name__ == "__main__":
    asyncio.run(main())
