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

    # Slots
    await db["slots"].create_index([("sport", 1), ("date", 1)])
    await db["slots"].create_index([("campus", 1), ("status", 1)])
    await db["slots"].create_index("date")
    print("  ✓ slots indexes")

    # Bookings
    await db["bookings"].create_index([("user_id", 1), ("status", 1)])
    await db["bookings"].create_index([("slot_id", 1), ("status", 1)])
    await db["bookings"].create_index("status")
    print("  ✓ bookings indexes")

    # Sessions
    await db["sessions"].create_index("refresh_token_hash", unique=True)
    await db["sessions"].create_index("expires_at", expireAfterSeconds=0)
    print("  ✓ sessions indexes (TTL on expires_at)")

    client.close()
    print("\nAll indexes created successfully!")


if __name__ == "__main__":
    asyncio.run(main())
