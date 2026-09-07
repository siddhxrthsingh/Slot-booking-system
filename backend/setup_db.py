"""
Run once to create MongoDB indexes for the slot booking system.
Usage:  python setup_db.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings


async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]

    print(f"Connected to: {settings.mongo_uri} / {settings.mongo_db_name}")

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
    # A user may have at most one booking document per slot, ever (rejoin
    # after leaving is blocked by product rule) — this also closes the
    # concurrent-duplicate-join race at the database layer.
    await db["bookings"].create_index([("user_id", 1), ("slot_id", 1)], unique=True)
    await db["bookings"].create_index([("user_id", 1), ("status", 1)])
    await db["bookings"].create_index([("slot_id", 1), ("status", 1)])
    await db["bookings"].create_index("status")
    await db["bookings"].create_index([("facility_id", 1), ("status", 1)])
    print("  ✓ bookings indexes")

    # Sessions
    await db["sessions"].create_index("refresh_token_hash", unique=True)
    await db["sessions"].create_index("expires_at", expireAfterSeconds=0)
    print("  ✓ sessions indexes (TTL on expires_at)")

    client.close()
    print("\nAll indexes created successfully!")


if __name__ == "__main__":
    asyncio.run(main())
