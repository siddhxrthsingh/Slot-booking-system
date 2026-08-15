from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase


DayType = Literal["weekday", "saturday", "sunday"]


def resolve_day_type(target_date: date | datetime) -> DayType:
    """Resolve schedule day type. Holiday support can be added here later."""
    weekday = target_date.weekday()
    if weekday == 5:
        return "saturday"
    if weekday == 6:
        return "sunday"
    return "weekday"


def normalize_slot_date(target_date: date | datetime) -> datetime:
    if isinstance(target_date, datetime):
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    return datetime.combine(target_date, time.min)


def _date_only(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _is_effective(template: dict, target_date: date | datetime) -> bool:
    requested = _date_only(target_date)
    effective_from = template.get("effective_from")
    effective_until = template.get("effective_until")

    if effective_from is not None and requested < _date_only(effective_from):
        return False
    if effective_until is not None and requested > _date_only(effective_until):
        return False
    return True


def _updated_sort_value(template: dict) -> datetime:
    value = template.get("updated_at") or template.get("created_at")
    return value if isinstance(value, datetime) else datetime.min


def _parse_minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _period_duration_minutes(period: dict) -> int:
    return _parse_minutes(period["end_time"]) - _parse_minutes(period["start_time"])


def _overlaps(start_time: str, end_time: str, other_start: str, other_end: str) -> bool:
    return (
        _parse_minutes(start_time) < _parse_minutes(other_end)
        and _parse_minutes(end_time) > _parse_minutes(other_start)
    )


async def resolve_template_for_facility(
    db: AsyncIOMotorDatabase,
    facility: dict,
    target_date: date | datetime,
    day_type: DayType,
) -> dict | None:
    candidates = await db["schedule_templates"].find(
        {
            "campus": facility["campus"],
            "sport": facility["sport"],
            "day_type": day_type,
            "is_active": True,
        }
    ).to_list(length=100)

    applicable = [template for template in candidates if _is_effective(template, target_date)]
    facility_templates = [
        template
        for template in applicable
        if template.get("facility_scope") == "facility"
        and template.get("facility_id") == facility["_id"]
    ]
    sport_templates = [
        template
        for template in applicable
        if template.get("facility_scope") == "sport"
    ]

    preferred = facility_templates or sport_templates
    if not preferred:
        return None

    return sorted(
        preferred,
        key=lambda template: (template.get("priority", 0), _updated_sort_value(template)),
        reverse=True,
    )[0]


async def _find_manual_overlaps(
    db: AsyncIOMotorDatabase,
    facility: dict,
    slot_date: datetime,
    start_time: str,
    end_time: str,
) -> list[dict[str, Any]]:
    manual_slots = await db["slots"].find(
        {
            "campus": facility["campus"],
            "facility_id": facility["_id"],
            "date": slot_date,
            "$or": [
                {"slot_type": "manual"},
                {"is_manual": True},
            ],
        }
    ).to_list(length=100)

    return [
        {
            "slot_id": str(slot.get("_id")),
            "facility_id": str(facility["_id"]),
            "facility_name": facility.get("display_name") or facility.get("name"),
            "start_time": start_time,
            "end_time": end_time,
            "manual_start_time": slot.get("start_time"),
            "manual_end_time": slot.get("end_time"),
        }
        for slot in manual_slots
        if slot.get("start_time")
        and slot.get("end_time")
        and _overlaps(start_time, end_time, slot["start_time"], slot["end_time"])
    ]


async def generate_slots_for_date(
    db: AsyncIOMotorDatabase,
    target_date: date | datetime,
    campus: str = "RR",
) -> dict[str, Any]:
    slot_date = normalize_slot_date(target_date)
    day_type = resolve_day_type(slot_date)
    now = datetime.now(timezone.utc)

    summary: dict[str, Any] = {
        "date": slot_date,
        "campus": campus,
        "day_type": day_type,
        "facilities_processed": 0,
        "slots_created": 0,
        "slots_existing": 0,
        "slots_skipped": 0,
        "errors": [],
        "manual_overlaps": [],
    }

    facilities = await db["facilities"].find(
        {"campus": campus, "is_active": True}
    ).sort([("sport", 1), ("sort_order", 1), ("name", 1)]).to_list(length=500)

    for facility in facilities:
        summary["facilities_processed"] += 1
        template = await resolve_template_for_facility(db, facility, slot_date, day_type)
        if not template:
            summary["slots_skipped"] += 1
            summary["errors"].append({
                "facility_id": str(facility["_id"]),
                "facility_name": facility.get("display_name") or facility.get("name"),
                "reason": "no_applicable_template",
            })
            continue

        for period in template.get("periods", []):
            if period.get("period_type") != "student" or not period.get("is_bookable", False):
                continue

            duration_minutes = _period_duration_minutes(period)
            if duration_minutes != 60 or period.get("duration_minutes") != 60:
                summary["slots_skipped"] += 1
                summary["errors"].append({
                    "facility_id": str(facility["_id"]),
                    "facility_name": facility.get("display_name") or facility.get("name"),
                    "start_time": period.get("start_time"),
                    "end_time": period.get("end_time"),
                    "reason": "invalid_student_period_duration",
                })
                continue

            overlaps = await _find_manual_overlaps(
                db,
                facility,
                slot_date,
                period["start_time"],
                period["end_time"],
            )
            summary["manual_overlaps"].extend(overlaps)

            identity = {
                "campus": facility["campus"],
                "facility_id": facility["_id"],
                "date": slot_date,
                "start_time": period["start_time"],
                "end_time": period["end_time"],
                "slot_type": "generated",
            }
            facility_name = facility.get("display_name") or facility.get("name")
            slot_doc = {
                **identity,
                "facility_name": facility_name,
                "sport": facility["sport"],
                "venue": facility_name,
                "capacity": facility["capacity"],
                "booked_count": 0,
                "status": "open",
                "duration_minutes": 60,
                "requires_approval": False,
                "leader_user_id": None,
                "created_by": None,
                "override_reason": None,
                "notes": None,
                "is_manual": False,
                "created_at": now,
                "updated_at": now,
            }

            result = await db["slots"].update_one(
                identity,
                {"$setOnInsert": slot_doc},
                upsert=True,
            )
            if result.upserted_id is not None:
                summary["slots_created"] += 1
            else:
                summary["slots_existing"] += 1

    return summary
