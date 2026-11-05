"""
Seed RR Campus facility configuration.

This script is additive and idempotent. It upserts facilities by the stable
identity: campus + sport + name.
"""
import asyncio
import argparse
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings
from app.models.facility import FacilityModel


RR_FACILITIES = [
    {
        "campus": "RR",
        "sport": "Badminton",
        "facility_type": "court",
        "name": "Court 1",
        "display_name": "Badminton Court 1",
        "capacity": 6,
        "is_active": True,
        "sort_order": 1,
    },
    {
        "campus": "RR",
        "sport": "Badminton",
        "facility_type": "court",
        "name": "Court 2",
        "display_name": "Badminton Court 2",
        "capacity": 6,
        "is_active": True,
        "sort_order": 2,
    },
    {
        "campus": "RR",
        "sport": "Badminton",
        "facility_type": "court",
        "name": "Court 3",
        "display_name": "Badminton Court 3",
        "capacity": 6,
        "is_active": True,
        "sort_order": 3,
    },
    {
        "campus": "RR",
        "sport": "Table Tennis",
        "facility_type": "table",
        "name": "Table 1",
        "display_name": "Table Tennis Table 1",
        "capacity": 6,
        "is_active": True,
        "sort_order": 1,
    },
    {
        "campus": "RR",
        "sport": "Table Tennis",
        "facility_type": "table",
        "name": "Table 2",
        "display_name": "Table Tennis Table 2",
        "capacity": 6,
        "is_active": True,
        "sort_order": 2,
    },
    {
        "campus": "RR",
        "sport": "Table Tennis",
        "facility_type": "table",
        "name": "Table 3",
        "display_name": "Table Tennis Table 3",
        "capacity": 6,
        "is_active": True,
        "sort_order": 3,
    },
    {
        "campus": "RR",
        "sport": "Squash",
        "facility_type": "court",
        "name": "Court 1",
        "display_name": "Squash Court 1",
        "capacity": 6,
        "is_active": True,
        "sort_order": 1,
    },
    {
        "campus": "RR",
        "sport": "Squash",
        "facility_type": "court",
        "name": "Court 2",
        "display_name": "Squash Court 2",
        "capacity": 6,
        "is_active": True,
        "sort_order": 2,
    },
    {
        "campus": "RR",
        "sport": "Basketball",
        "facility_type": "court",
        "name": "Court 1",
        "display_name": "Basketball Court 1",
        "capacity": 12,
        "is_active": True,
        "sort_order": 1,
    },
    {
        "campus": "RR",
        "sport": "Basketball",
        "facility_type": "court",
        "name": "Court 2",
        "display_name": "Basketball Court 2",
        "capacity": 12,
        "is_active": True,
        "sort_order": 2,
    },
    {
        "campus": "RR",
        "sport": "Volleyball",
        "facility_type": "court",
        "name": "Court 1",
        "display_name": "Volleyball Court 1",
        "capacity": 12,
        "is_active": True,
        "sort_order": 1,
    },
]


async def seed_rr_facilities(db: AsyncIOMotorDatabase) -> dict:
    now = datetime.now(timezone.utc)
    inserted = 0
    matched = 0
    modified = 0

    for facility in RR_FACILITIES:
        FacilityModel(**facility)
        identity = {
            "campus": facility["campus"],
            "sport": facility["sport"],
            "name": facility["name"],
        }
        result = await db["facilities"].update_one(
            identity,
            {
                "$set": {**facility, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted += 1
        else:
            matched += result.matched_count
            modified += result.modified_count

    return {
        "expected": len(RR_FACILITIES),
        "inserted": inserted,
        "matched": matched,
        "modified": modified,
    }


async def verify_rr_facilities(db: AsyncIOMotorDatabase) -> dict:
    expected_keys = {
        (facility["campus"], facility["sport"], facility["name"])
        for facility in RR_FACILITIES
    }
    docs = await db["facilities"].find(
        {"campus": "RR"},
        {"_id": 0},
    ).sort([("sport", 1), ("sort_order", 1), ("name", 1)]).to_list(length=100)

    seen: dict[tuple[str, str, str], int] = {}
    mismatches = []
    for doc in docs:
        key = (doc.get("campus"), doc.get("sport"), doc.get("name"))
        seen[key] = seen.get(key, 0) + 1
        expected = next(
            (facility for facility in RR_FACILITIES if key == (
                facility["campus"], facility["sport"], facility["name"]
            )),
            None,
        )
        if expected is None:
            mismatches.append({"identity": key, "issue": "unexpected"})
            continue
        for field, value in expected.items():
            if doc.get(field) != value:
                mismatches.append({
                    "identity": key,
                    "field": field,
                    "expected": value,
                    "actual": doc.get(field),
                })

    missing = sorted(expected_keys - set(seen))
    duplicates = {key: count for key, count in seen.items() if count > 1}

    return {
        "expected": len(expected_keys),
        "found_expected_identities": len(expected_keys & set(seen)),
        "total_rr_facility_docs": len(docs),
        "missing": missing,
        "duplicates": duplicates,
        "mismatches": mismatches,
        "ok": not missing and not duplicates and not mismatches and len(docs) == len(expected_keys),
    }


async def main():
    parser = argparse.ArgumentParser(description="Seed or verify RR Campus facilities.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify RR facilities without upserting documents.",
    )
    args = parser.parse_args()

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]

    try:
        await client.admin.command("ping")
        print(f"Connected to: {settings.mongo_db_name}")

        seed_result = None if args.verify_only else await seed_rr_facilities(db)
        verify_result = await verify_rr_facilities(db)

        if seed_result is not None:
            print(f"Seed result: {seed_result}")
        print(f"Verify result: {verify_result}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
