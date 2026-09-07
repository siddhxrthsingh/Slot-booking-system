import unittest
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.services.booking_service import get_user_bookings


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None):
        query = query or {}
        return FakeCursor([doc for doc in self.docs if _matches(doc, query)])

    async def find_one(self, query):
        for doc in self.docs:
            if _matches(doc, query):
                return doc
        return None


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, key, direction=None):
        reverse = (direction if direction is not None else 1) < 0
        self.docs.sort(key=lambda d: d.get(key), reverse=reverse)
        return self

    async def to_list(self, length):
        return self.docs[:length]


def _matches(doc, query):
    for key, expected in query.items():
        if doc.get(key) != expected:
            return False
    return True


class FakeDb:
    def __init__(self, bookings=None, slots=None):
        self.collections = {
            "bookings": FakeCollection(bookings),
            "slots": FakeCollection(slots),
        }

    def __getitem__(self, name):
        return self.collections[name]


def _slot(**overrides):
    base = {
        "_id": ObjectId(),
        "date": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
        "start_time": "09:00",
        "end_time": "10:00",
        "duration_minutes": 60,
        "venue": "Badminton Court 1",
        "campus": "RR",
    }
    base.update(overrides)
    return base


def _booking(user_id, slot_id, **overrides):
    base = {
        "_id": ObjectId(),
        "user_id": user_id,
        "slot_id": slot_id,
        "sport": "Badminton",
        "status": "confirmed",
        "booking_date": datetime.now(timezone.utc),
        "cancelled_at": None,
        "notes": None,
        "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


class MyBookingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_upcoming_confirmed_booking_is_not_marked_past(self):
        user_id = ObjectId()
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        slot = _slot(date=future.replace(hour=0, minute=0, second=0, microsecond=0),
                     start_time=f"{future.hour:02d}:00", end_time=f"{(future.hour + 1) % 24:02d}:00")
        booking = _booking(user_id, slot["_id"])
        db = FakeDb(bookings=[booking], slots=[slot])

        result = await get_user_bookings(db, str(user_id))

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["is_past"])
        self.assertEqual(result[0]["status"], "confirmed")

    async def test_booking_for_elapsed_slot_is_marked_past(self):
        user_id = ObjectId()
        past = datetime.now(timezone.utc) - timedelta(days=27)
        slot = _slot(date=past.replace(hour=0, minute=0, second=0, microsecond=0),
                     start_time="09:00", end_time="10:00")
        booking = _booking(user_id, slot["_id"])
        db = FakeDb(bookings=[booking], slots=[slot])

        result = await get_user_bookings(db, str(user_id))

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_past"])
        # Historical record itself is untouched/preserved, not deleted.
        self.assertEqual(result[0]["status"], "confirmed")

    async def test_cancelled_booking_remains_present_for_history(self):
        user_id = ObjectId()
        future = datetime.now(timezone.utc) + timedelta(days=1)
        slot = _slot(date=future.replace(hour=0, minute=0, second=0, microsecond=0))
        booking = _booking(user_id, slot["_id"], status="cancelled",
                            cancelled_at=datetime.now(timezone.utc))
        db = FakeDb(bookings=[booking], slots=[slot])

        result = await get_user_bookings(db, str(user_id))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "cancelled")

    async def test_booking_with_missing_slot_is_marked_past(self):
        user_id = ObjectId()
        booking = _booking(user_id, ObjectId())  # slot never generated/deleted
        db = FakeDb(bookings=[booking], slots=[])

        result = await get_user_bookings(db, str(user_id))

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_past"])


if __name__ == "__main__":
    unittest.main()
