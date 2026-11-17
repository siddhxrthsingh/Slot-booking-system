"""
Standalone: create ONLY the unique partial index that enforces the
one-active-booking-per-student-per-day policy. Safe to run on its own.

  python create_active_day_index.py            # prints the plan, creates nothing
  python create_active_day_index.py --apply    # creates the index

Never drops or modifies anything. Legacy bookings have no `active_day_key`
and are excluded from the index, so no existing data can violate it.
"""
import argparse
import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        coll = client[settings.mongo_db_name]["bookings"]
        print(f"Database: {settings.mongo_db_name}  mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        dupes = await coll.aggregate([
            {"$match": {"active_day_key": {"$type": "string"}}},
            {"$group": {"_id": "$active_day_key", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
        ]).to_list(length=20)
        print(f"existing duplicate active_day_key values: {len(dupes)}")
        if dupes:
            print("Resolve duplicates before creating the unique index:", dupes)
            return
        if args.apply:
            name = await coll.create_index(
                "active_day_key",
                unique=True,
                partialFilterExpression={"active_day_key": {"$type": "string"}},
            )
            print("index ready:", name)
        else:
            print("would create unique partial index on bookings.active_day_key")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
