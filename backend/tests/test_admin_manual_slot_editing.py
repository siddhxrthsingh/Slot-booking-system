import unittest
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.services.admin_service import update_manual_slot
from tests.test_admin_manual_slot_creation import make_facility, future_date


def make_manual_slot(facility, **overrides):
    base = {
        "_id": ObjectId(),
        "facility_id": facility["_id"],
        "facility_name": facility["display_name"],
        "sport": facility["sport"],
        "date": future_date(),
        "start_time": "18:00",
        "end_time": "19:00",
        "duration_minutes": 60,
        "venue": facility["display_name"],
        "campus": "RR",
        "capacity": facility["capacity"],
        "booked_count": 0,
        "status": "open",
        "slot_type": "manual",
        "is_manual": True,
    }
    base.update(overrides)
    return base


class ManualSlotEditingTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_manual_slot_edit(self):
        facility = make_facility()
        slot = make_manual_slot(facility)
        db = _fake_db([slot], [facility])

        updated = await update_manual_slot(
            db, str(slot["_id"]),
            {"start_time": "20:00", "end_time": "21:00"},
        )

        self.assertEqual(updated["start_time"], "20:00")
        self.assertEqual(updated["end_time"], "21:00")
        self.assertTrue(updated["is_manual"])

    async def test_facility_derived_fields_and_capacity_on_edit(self):
        old_facility = make_facility(sport="Badminton", display_name="Badminton Court 1", capacity=6)
        new_facility = make_facility(sport="Squash", display_name="Squash Court 2", capacity=6)
        slot = make_manual_slot(old_facility)
        db = _fake_db([slot], [old_facility, new_facility])

        updated = await update_manual_slot(
            db, str(slot["_id"]),
            {"facility_id": str(new_facility["_id"])},
        )

        self.assertEqual(updated["sport"], "Squash")
        self.assertEqual(updated["facility_name"], "Squash Court 2")
        self.assertEqual(updated["venue"], "Squash Court 2")
        self.assertEqual(updated["capacity"], 6)
        self.assertEqual(str(updated["facility_id"]), str(new_facility["_id"]))

    async def test_overlap_with_other_slot_rejected(self):
        facility = make_facility()
        date = future_date()
        slot_a = make_manual_slot(facility, date=date, start_time="09:00", end_time="10:00")
        slot_b = make_manual_slot(facility, date=date, start_time="14:00", end_time="15:00")
        db = _fake_db([slot_a, slot_b], [facility])

        with self.assertRaises(ValueError):
            await update_manual_slot(
                db, str(slot_b["_id"]),
                {"start_time": "09:30", "end_time": "10:30"},  # overlaps slot_a
            )

    async def test_invalid_time_rejected(self):
        facility = make_facility()
        slot = make_manual_slot(facility)
        db = _fake_db([slot], [facility])

        with self.assertRaises(ValueError):
            await update_manual_slot(
                db, str(slot["_id"]),
                {"start_time": "10:00", "end_time": "09:00"},
            )

    async def test_generated_slot_cannot_be_edited_through_manual_flow(self):
        facility = make_facility()
        generated_slot = make_manual_slot(facility, is_manual=False, slot_type="generated")
        db = _fake_db([generated_slot], [facility])

        with self.assertRaises(ValueError):
            await update_manual_slot(
                db, str(generated_slot["_id"]),
                {"start_time": "20:00", "end_time": "21:00"},
            )

    async def test_edit_conflicting_with_active_participants_rejected(self):
        facility = make_facility(capacity=6)
        other_facility = make_facility(sport="Volleyball", display_name="Volleyball Court 1", capacity=12)
        slot = make_manual_slot(facility, booked_count=2)
        booking = {
            "_id": ObjectId(),
            "slot_id": slot["_id"],
            "user_id": ObjectId(),
            "status": "confirmed",
        }
        db = _fake_db([slot], [facility, other_facility], bookings=[booking])

        with self.assertRaises(ValueError):
            await update_manual_slot(
                db, str(slot["_id"]),
                {"facility_id": str(other_facility["_id"])},
            )


# ---------------------------------------------------------------------------
# Minimal fake db supporting find/find_one/find_one_and_update/count_documents
# ---------------------------------------------------------------------------

def _matches(doc, query):
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$gte" in expected and not (actual is not None and actual >= expected["$gte"]):
                return False
            if "$lt" in expected and not (actual is not None and actual < expected["$lt"]):
                return False
            continue
        if actual != expected:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *a, **k):
        return self

    async def to_list(self, length):
        return self.docs[:length]


class _FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query=None):
        query = query or {}
        return _FakeCursor([d for d in self.docs if _matches(d, query)])

    async def find_one(self, query):
        for d in self.docs:
            if _matches(d, query):
                return d
        return None

    async def find_one_and_update(self, query, update, return_document=True):
        for d in self.docs:
            if _matches(d, query):
                for op, fields in update.items():
                    if op == "$set":
                        d.update(fields)
                return d
        return None

    async def count_documents(self, query):
        return len([d for d in self.docs if _matches(d, query)])


class _FakeDb:
    def __init__(self, collections):
        self.collections = collections

    def __getitem__(self, name):
        return self.collections[name]


def _fake_db(slots, facilities, bookings=None):
    return _FakeDb({
        "slots": _FakeCollection(slots),
        "facilities": _FakeCollection(facilities),
        "bookings": _FakeCollection(bookings or []),
    })


if __name__ == "__main__":
    unittest.main()
