"""
Seed confirmed RR Campus schedule templates.

This script is additive and idempotent. It only upserts schedule_templates and
does not generate slots or modify users, facilities, bookings, or slots.

College holiday schedules will resolve to Sunday templates later; no holiday
templates are stored by this seed.
"""
import argparse
import asyncio
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings
from app.models.schedule_template import ScheduleTemplateModel


TARGET_SPORTS = ["Badminton", "Table Tennis", "Squash", "Basketball", "Volleyball"]


def period(start: str, end: str, period_type: str) -> dict[str, Any]:
    return {
        "start_time": start,
        "end_time": end,
        "period_type": period_type,
        "duration_minutes": 60,
        "is_bookable": period_type == "student",
        "label": period_type.title(),
    }


INDOOR_WEEKDAY_PERIODS = [
    period("06:00", "07:00", "student"),
    period("07:00", "08:00", "student"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
    period("10:00", "11:00", "student"),
    period("11:00", "12:00", "student"),
    period("12:00", "13:00", "student"),
    period("13:00", "14:00", "lunch"),
    period("14:00", "15:00", "student"),
    period("15:00", "16:00", "student"),
    period("16:00", "17:00", "student"),
    period("17:00", "18:00", "student"),
    period("18:00", "19:00", "student"),
]

BADMINTON_COURT_1_WEEKDAY_PERIODS = [
    period("06:00", "07:00", "staff"),
    period("07:00", "08:00", "staff"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
    period("10:00", "11:00", "student"),
    period("11:00", "12:00", "student"),
    period("12:00", "13:00", "student"),
    period("13:00", "14:00", "lunch"),
    period("14:00", "15:00", "student"),
    period("15:00", "16:00", "student"),
    period("16:00", "17:00", "staff"),
    period("17:00", "18:00", "staff"),
    period("18:00", "19:00", "staff"),
]

INDOOR_SATURDAY_PERIODS = [
    period("06:00", "07:00", "student"),
    period("07:00", "08:00", "student"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
    period("10:00", "11:00", "student"),
    period("11:00", "12:00", "student"),
    period("12:00", "13:00", "student"),
]

BADMINTON_COURT_1_SATURDAY_PERIODS = [
    period("06:00", "07:00", "staff"),
    period("07:00", "08:00", "staff"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
    period("10:00", "11:00", "student"),
    period("11:00", "12:00", "student"),
    period("12:00", "13:00", "student"),
]

INDOOR_SUNDAY_PERIODS = [
    period("06:00", "07:00", "student"),
    period("07:00", "08:00", "student"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
]

BADMINTON_COURT_1_SUNDAY_PERIODS = [
    period("06:00", "07:00", "staff"),
    period("07:00", "08:00", "staff"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
]

BASKETBALL_VOLLEYBALL_WEEKDAY_PERIODS = [
    period("09:00", "10:00", "student"),
    period("10:00", "11:00", "student"),
    period("11:00", "12:00", "student"),
    period("12:00", "13:00", "student"),
    period("13:00", "14:00", "lunch"),
    period("14:00", "15:00", "student"),
    period("15:00", "16:00", "student"),
    period("16:00", "17:00", "student"),
    period("17:00", "18:00", "student"),
    period("18:00", "19:00", "student"),
]


async def build_rr_schedule_templates(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    court_1 = await db["facilities"].find_one(
        {"campus": "RR", "sport": "Badminton", "name": "Court 1"},
        {"_id": 1, "display_name": 1},
    )
    if not court_1:
        raise RuntimeError(
            "Badminton Court 1 facility not found. Run seed_facilities.py first."
        )

    templates: list[dict[str, Any]] = []
    for sport in ("Badminton", "Table Tennis", "Squash"):
        templates.extend([
            {
                "campus": "RR",
                "sport": sport,
                "facility_scope": "sport",
                "facility_id": None,
                "facility_name": None,
                "day_type": "weekday",
                "periods": INDOOR_WEEKDAY_PERIODS,
                "priority": 10,
                "notes": "Sport-level weekday template.",
            },
            {
                "campus": "RR",
                "sport": sport,
                "facility_scope": "sport",
                "facility_id": None,
                "facility_name": None,
                "day_type": "saturday",
                "periods": INDOOR_SATURDAY_PERIODS,
                "priority": 10,
                "notes": "Sport-level Saturday template. No lunch period.",
            },
            {
                "campus": "RR",
                "sport": sport,
                "facility_scope": "sport",
                "facility_id": None,
                "facility_name": None,
                "day_type": "sunday",
                "periods": INDOOR_SUNDAY_PERIODS,
                "priority": 10,
                "notes": "Sport-level Sunday template. College holidays resolve to Sunday later.",
            },
        ])

    templates.extend([
        {
            "campus": "RR",
            "sport": "Badminton",
            "facility_scope": "facility",
            "facility_id": court_1["_id"],
            "facility_name": court_1.get("display_name", "Badminton Court 1"),
            "day_type": "weekday",
            "periods": BADMINTON_COURT_1_WEEKDAY_PERIODS,
            "priority": 100,
            "notes": "Badminton Court 1 weekday staff override.",
        },
        {
            "campus": "RR",
            "sport": "Badminton",
            "facility_scope": "facility",
            "facility_id": court_1["_id"],
            "facility_name": court_1.get("display_name", "Badminton Court 1"),
            "day_type": "saturday",
            "periods": BADMINTON_COURT_1_SATURDAY_PERIODS,
            "priority": 100,
            "notes": "Badminton Court 1 Saturday staff override.",
        },
        {
            "campus": "RR",
            "sport": "Badminton",
            "facility_scope": "facility",
            "facility_id": court_1["_id"],
            "facility_name": court_1.get("display_name", "Badminton Court 1"),
            "day_type": "sunday",
            "periods": BADMINTON_COURT_1_SUNDAY_PERIODS,
            "priority": 100,
            "notes": "Badminton Court 1 Sunday staff override. College holidays resolve to Sunday later.",
        },
        {
            "campus": "RR",
            "sport": "Basketball",
            "facility_scope": "sport",
            "facility_id": None,
            "facility_name": None,
            "day_type": "weekday",
            "periods": BASKETBALL_VOLLEYBALL_WEEKDAY_PERIODS,
            "priority": 10,
            "notes": "Basketball weekday template. Cleaning schedule unknown; no cleaning period represented.",
        },
        {
            "campus": "RR",
            "sport": "Volleyball",
            "facility_scope": "sport",
            "facility_id": None,
            "facility_name": None,
            "day_type": "weekday",
            "periods": BASKETBALL_VOLLEYBALL_WEEKDAY_PERIODS,
            "priority": 10,
            "notes": "Volleyball weekday template. Cleaning schedule unknown; no cleaning period represented.",
        },
    ])
    return templates


def template_identity(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "campus": template["campus"],
        "sport": template["sport"],
        "facility_scope": template["facility_scope"],
        "facility_id": template.get("facility_id"),
        "day_type": template["day_type"],
    }


async def seed_rr_schedule_templates(db: AsyncIOMotorDatabase) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    inserted = 0
    matched = 0
    modified = 0

    templates = await build_rr_schedule_templates(db)
    for template in templates:
        doc = {
            **template,
            "is_active": True,
            "effective_from": None,
            "effective_until": None,
            "created_by": None,
        }
        ScheduleTemplateModel(**doc)
        result = await db["schedule_templates"].update_one(
            template_identity(doc),
            {
                "$set": {**doc, "updated_at": now},
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
        "expected": len(templates),
        "inserted": inserted,
        "matched": matched,
        "modified": modified,
    }


async def verify_rr_schedule_templates(db: AsyncIOMotorDatabase) -> dict[str, Any]:
    expected_templates = await build_rr_schedule_templates(db)
    expected_keys = {
        tuple(template_identity(template).items())
        for template in expected_templates
    }

    docs = await db["schedule_templates"].find(
        {"campus": "RR", "sport": {"$in": TARGET_SPORTS}},
        {"_id": 0},
    ).to_list(length=100)

    seen: dict[tuple[tuple[str, Any], ...], int] = {}
    mismatches = []
    for doc in docs:
        identity = template_identity(doc)
        key = tuple(identity.items())
        seen[key] = seen.get(key, 0) + 1
        expected = next(
            (
                template
                for template in expected_templates
                if template_identity(template) == identity
            ),
            None,
        )
        if expected is None:
            mismatches.append({"identity": identity, "issue": "unexpected"})
            continue
        for field in ("facility_name", "facility_scope", "day_type", "priority", "periods"):
            if doc.get(field) != expected.get(field):
                mismatches.append({
                    "identity": identity,
                    "field": field,
                    "expected": expected.get(field),
                    "actual": doc.get(field),
                })

    missing = [dict(key) for key in sorted(expected_keys - set(seen), key=str)]
    duplicates = {str(dict(key)): count for key, count in seen.items() if count > 1}
    holiday_count = await db["schedule_templates"].count_documents({"campus": "RR", "day_type": "holiday"})

    sport_day_types = {}
    for sport in TARGET_SPORTS:
        sport_day_types[sport] = sorted({
            doc.get("day_type")
            for doc in docs
            if doc.get("sport") == sport and doc.get("facility_scope") == "sport"
        })

    basketball_cleaning = any(
        period.get("period_type") == "cleaning"
        for doc in docs
        if doc.get("sport") == "Basketball"
        for period in doc.get("periods", [])
    )
    volleyball_cleaning = any(
        period.get("period_type") == "cleaning"
        for doc in docs
        if doc.get("sport") == "Volleyball"
        for period in doc.get("periods", [])
    )

    court_1_overrides = sorted(
        doc.get("day_type")
        for doc in docs
        if doc.get("sport") == "Badminton" and doc.get("facility_scope") == "facility"
    )

    return {
        "expected": len(expected_templates),
        "found_expected_identities": len(expected_keys & set(seen)),
        "total_rr_default_template_docs": len(docs),
        "missing": missing,
        "duplicates": duplicates,
        "mismatches": mismatches,
        "badminton_court_1_overrides": court_1_overrides,
        "sport_day_types": sport_day_types,
        "basketball_has_cleaning": basketball_cleaning,
        "volleyball_has_cleaning": volleyball_cleaning,
        "holiday_template_count": holiday_count,
        "ok": (
            not missing
            and not duplicates
            and not mismatches
            and len(docs) == len(expected_templates)
            and court_1_overrides == ["saturday", "sunday", "weekday"]
            and sport_day_types["Basketball"] == ["weekday"]
            and sport_day_types["Volleyball"] == ["weekday"]
            and not basketball_cleaning
            and not volleyball_cleaning
            and holiday_count == 0
        ),
    }


async def main():
    parser = argparse.ArgumentParser(description="Seed or verify RR schedule templates.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify RR schedule templates without upserting documents.",
    )
    args = parser.parse_args()

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]

    try:
        await client.admin.command("ping")
        print(f"Connected to: {settings.mongo_db_name}")

        seed_result = None if args.verify_only else await seed_rr_schedule_templates(db)
        verify_result = await verify_rr_schedule_templates(db)

        if seed_result is not None:
            print(f"Seed result: {seed_result}")
        print(f"Verify result: {verify_result}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
