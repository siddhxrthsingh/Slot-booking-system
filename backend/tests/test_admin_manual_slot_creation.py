import unittest
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.services.admin_service import create_slot
from tests.test_booking_join_service import FakeDb


def make_facility(**overrides):
    base = {
        "_id": ObjectId(),
        "campus": "RR",
        "sport": "Badminton",
        "facility_type": "court",
        "name": "Court 1",
        "display_name": "Badminton Court 1",
        "capacity": 6,
        "is_active": True,
        "sort_order": 1,
    }
    base.update(overrides)
    return base


def future_date(days=3):
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


class ManualSlotCreationTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_facility_creates_manual_slot(self):
        facility = make_facility()
        db = FakeDb(slots=[], facilities=[facility])
        admin_id = str(ObjectId())

        slot = await create_slot(
            db,
            {
                "facility_id": str(facility["_id"]),
                "date": future_date(),
                "start_time": "18:00",
                "end_time": "19:30",
            },
            admin_id,
        )

        self.assertTrue(slot["is_manual"])
        self.assertEqual(slot["slot_type"], "manual")
        self.assertEqual(slot["status"], "open")
        self.assertEqual(slot["booked_count"], 0)

    async def test_sport_facility_name_and_capacity_come_from_facility(self):
        facility = make_facility(sport="Squash", display_name="Squash Court 2", capacity=6)
        db = FakeDb(slots=[], facilities=[facility])

        # Deliberately do NOT pass sport/venue/capacity — the schema no
        # longer accepts them, and even if extra keys were present in the
        # dict, create_slot must not trust them.
        slot = await create_slot(
            db,
            {
                "facility_id": str(facility["_id"]),
                "date": future_date(),
                "start_time": "09:00",
                "end_time": "10:00",
                "sport": "Football",       # should be ignored
                "venue": "Fake Venue",     # should be ignored
                "capacity": 999,           # should be ignored
            },
            str(ObjectId()),
        )

        self.assertEqual(slot["sport"], "Squash")
        self.assertEqual(slot["facility_name"], "Squash Court 2")
        self.assertEqual(slot["venue"], "Squash Court 2")
        self.assertEqual(slot["capacity"], 6)

    async def test_missing_facility_rejected(self):
        db = FakeDb(slots=[], facilities=[])

        with self.assertRaises(LookupError):
            await create_slot(
                db,
                {
                    "facility_id": str(ObjectId()),
                    "date": future_date(),
                    "start_time": "09:00",
                    "end_time": "10:00",
                },
                str(ObjectId()),
            )

    async def test_inactive_facility_rejected(self):
        facility = make_facility(is_active=False)
        db = FakeDb(slots=[], facilities=[facility])

        with self.assertRaises(ValueError):
            await create_slot(
                db,
                {
                    "facility_id": str(facility["_id"]),
                    "date": future_date(),
                    "start_time": "09:00",
                    "end_time": "10:00",
                },
                str(ObjectId()),
            )

    async def test_invalid_time_rejected(self):
        facility = make_facility()
        db = FakeDb(slots=[], facilities=[facility])

        with self.assertRaises(ValueError):
            await create_slot(
                db,
                {
                    "facility_id": str(facility["_id"]),
                    "date": future_date(),
                    "start_time": "10:00",
                    "end_time": "09:00",  # end before start
                },
                str(ObjectId()),
            )

    async def test_overlapping_facility_slot_rejected(self):
        facility = make_facility()
        date = future_date()
        existing_slot = {
            "_id": ObjectId(),
            "facility_id": facility["_id"],
            "facility_name": facility["display_name"],
            "sport": facility["sport"],
            "date": date,
            "start_time": "09:00",
            "end_time": "10:30",
            "duration_minutes": 90,
            "campus": "RR",
            "capacity": 6,
            "booked_count": 0,
            "status": "open",
        }
        db = FakeDb(slots=[existing_slot], facilities=[facility])

        with self.assertRaises(ValueError):
            await create_slot(
                db,
                {
                    "facility_id": str(facility["_id"]),
                    "date": date,
                    "start_time": "10:00",  # overlaps 09:00-10:30
                    "end_time": "11:00",
                },
                str(ObjectId()),
            )

    async def test_existing_generated_slots_are_not_modified(self):
        facility = make_facility()
        date = future_date()
        generated_slot = {
            "_id": ObjectId(),
            "facility_id": facility["_id"],
            "facility_name": facility["display_name"],
            "sport": facility["sport"],
            "date": date,
            "start_time": "09:00",
            "end_time": "10:00",
            "duration_minutes": 60,
            "campus": "RR",
            "capacity": 6,
            "booked_count": 2,
            "status": "open",
            "slot_type": "generated",
            "is_manual": False,
        }
        db = FakeDb(slots=[generated_slot], facilities=[facility])
        snapshot_before = dict(generated_slot)

        # Create a non-overlapping manual slot the same day.
        await create_slot(
            db,
            {
                "facility_id": str(facility["_id"]),
                "date": date,
                "start_time": "14:00",
                "end_time": "15:00",
            },
            str(ObjectId()),
        )

        stored_generated = next(
            s for s in db["slots"].docs if s["_id"] == generated_slot["_id"]
        )
        self.assertEqual(stored_generated, snapshot_before)
        self.assertEqual(len(db["slots"].docs), 2)


if __name__ == "__main__":
    unittest.main()
