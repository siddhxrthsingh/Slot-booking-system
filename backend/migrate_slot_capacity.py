"""
Pilot policy migration: align already-generated FUTURE slots with the current
facility capacity (6 -> 4; 12 stays 12).

Changing seed_facilities.py / the facility documents does NOT update existing
slot documents (slots snapshot `capacity` at generation time). This script
does that, safely:

  * DRY-RUN by default. Nothing is written unless --apply is passed.
  * Only slots whose end time is still in the future are considered; past
    slots are never touched. Cancelled/closed slots are skipped.
  * Only `capacity` (and `status` open<->full) are changed. No slot or booking
    is deleted, recreated or cancelled; no participant is removed.
  * Each write is guarded on the values that were read, so a join/leave that
    lands mid-migration cannot be overwritten (the slot is reported as
    "skipped_concurrent" - just re-run).
  * Slots already holding MORE active participants than the new capacity are
    NOT trimmed. They are marked full (no further joins), stamped with
    `needs_capacity_review: true`, and listed in the report for manual review.

Order of operations:  1) python seed_facilities.py   (updates facility docs)
                      2) python migrate_slot_capacity.py            (dry-run)
                      3) python migrate_slot_capacity.py --apply
"""
import argparse
import asyncio
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings
from app.services.booking_service import _slot_end_dt


async def migrate_slot_capacity(
    db: AsyncIOMotorDatabase, apply: bool = False, now: datetime | None = None
) -> dict:
    now = now or datetime.now(timezone.utc)
    report = {
        "applied": apply,
        "examined": 0,
        "updated": [],
        "over_capacity_flagged": [],
        "skipped_concurrent": [],
        "skipped_past_or_inactive": 0,
    }

    facilities = await db["facilities"].find({}).to_list(length=500)
    for facility in facilities:
        target = facility.get("capacity")
        if target is None:
            continue

        slots = await db["slots"].find(
            {"facility_id": facility["_id"], "capacity": {"$ne": target}}
        ).to_list(length=100000)

        for slot in slots:
            report["examined"] += 1
            if slot.get("status") not in ("open", "full"):
                report["skipped_past_or_inactive"] += 1
                continue
            try:
                if _slot_end_dt(slot) <= now:
                    report["skipped_past_or_inactive"] += 1
                    continue
            except Exception:
                # Unparseable date: leave it alone rather than guess.
                report["skipped_past_or_inactive"] += 1
                continue

            booked = slot.get("booked_count", 0)
            old_capacity = slot.get("capacity")
            entry = {
                "slot_id": str(slot["_id"]),
                "facility": facility.get("display_name"),
                "date": str(slot.get("date")),
                "start_time": slot.get("start_time"),
                "old_capacity": old_capacity,
                "new_capacity": target,
                "booked_count": booked,
            }
            over = booked > target
            new_status = "full" if booked >= target else "open"

            if over:
                report["over_capacity_flagged"].append(entry)
            else:
                report["updated"].append(entry)

            if not apply:
                continue

            fields = {"capacity": target, "status": new_status, "updated_at": now}
            if over:
                fields["needs_capacity_review"] = True
                fields["capacity_review_note"] = (
                    f"Pilot capacity reduced {old_capacity}->{target} but {booked} "
                    "participants were already joined. Nobody was removed; "
                    "slot is closed to new joins. Review manually."
                )
            # Guarded on exactly what we read: a concurrent join/leave changes
            # booked_count or status and makes this a no-op.
            res = await db["slots"].update_one(
                {
                    "_id": slot["_id"],
                    "capacity": old_capacity,
                    "booked_count": booked,
                    "status": slot.get("status"),
                },
                {"$set": fields},
            )
            if getattr(res, "matched_count", 1) == 0:
                bucket = "over_capacity_flagged" if over else "updated"
                report[bucket].pop()
                report["skipped_concurrent"].append(entry)

    return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    args = parser.parse_args()

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]
    try:
        print(f"Database: {settings.mongo_db_name}  mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        report = await migrate_slot_capacity(db, apply=args.apply)
        print(f"examined={report['examined']} "
              f"to_update={len(report['updated'])} "
              f"over_capacity={len(report['over_capacity_flagged'])} "
              f"skipped_concurrent={len(report['skipped_concurrent'])} "
              f"skipped_past_or_inactive={report['skipped_past_or_inactive']}")
        for e in report["over_capacity_flagged"]:
            print("  REVIEW:", e)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
