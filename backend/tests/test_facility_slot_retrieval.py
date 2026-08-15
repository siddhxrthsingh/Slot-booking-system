import unittest
from datetime import datetime, timedelta, timezone

from app.services.booking_service import list_available_slots, serialize_student_slot


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, sort_spec):
        if isinstance(sort_spec, str):
            self.docs.sort(key=lambda doc: doc.get(sort_spec))
            return self
        for key, direction in reversed(sort_spec):
            self.docs.sort(key=lambda doc: doc.get(key) or "", reverse=direction < 0)
        return self

    async def to_list(self, length):
        return self.docs[:length]


class FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query):
        return FakeCursor([doc for doc in self.docs if matches(doc, query)])


class FakeDb:
    def __init__(self, slots):
        self.collections = {"slots": FakeCollection(slots)}

    def __getitem__(self, name):
        return self.collections[name]


def matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(matches(doc, clause) for clause in expected):
                return False
            continue
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$gte" in expected and actual < expected["$gte"]:
                return False
            if "$lte" in expected and actual > expected["$lte"]:
                return False
            if "$regex" in expected and expected["$regex"].lower() not in str(actual or "").lower():
                return False
            continue
        if actual != expected:
            return False
    return True


def future_date():
    return (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def slot(**overrides):
    base = {
        "_id": overrides.get("_id", "slot-1"),
        "facility_id": overrides.get("facility_id", "facility-1"),
        "facility_name": overrides.get("facility_name", "Badminton Court 1"),
        "sport": overrides.get("sport", "Badminton"),
        "date": overrides.get("date", future_date()),
        "start_time": overrides.get("start_time", "09:00"),
        "end_time": overrides.get("end_time", "10:00"),
        "venue": overrides.get("venue"),
        "campus": overrides.get("campus", "RR"),
        "capacity": overrides.get("capacity", 6),
        "booked_count": overrides.get("booked_count", 0),
        "status": overrides.get("status", "open"),
        "duration_minutes": overrides.get("duration_minutes", 60),
        "slot_type": overrides.get("slot_type", "generated"),
        "is_manual": overrides.get("is_manual", False),
        "requires_approval": overrides.get("requires_approval", False),
    }
    base.update(overrides)
    return base


class FacilitySlotRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_facilities_for_one_sport_date_are_returned(self):
        date = future_date()
        db = FakeDb([
            slot(_id="slot-1", facility_id="facility-1", facility_name="Badminton Court 1", date=date),
            slot(_id="slot-2", facility_id="facility-2", facility_name="Badminton Court 2", date=date),
        ])

        result = await list_available_slots(db, sport="Badminton", date=date, campus="RR")

        self.assertEqual(len(result), 2)
        self.assertEqual({item["facility_name"] for item in result}, {"Badminton Court 1", "Badminton Court 2"})

    async def test_full_slots_are_returned_with_zero_available_count(self):
        date = future_date()
        db = FakeDb([slot(date=date, booked_count=6, capacity=6, status="full")])

        result = await list_available_slots(db, sport="Badminton", date=date, campus="RR")
        serialized = serialize_student_slot(result[0])

        self.assertEqual(serialized["status"], "full")
        self.assertEqual(serialized["available_count"], 0)

    async def test_available_count_is_never_negative(self):
        serialized = serialize_student_slot(slot(booked_count=8, capacity=6, status="full"))

        self.assertEqual(serialized["available_count"], 0)

    async def test_closed_and_cancelled_slots_are_not_student_available(self):
        date = future_date()
        db = FakeDb([
            slot(_id="open", date=date, status="open"),
            slot(_id="closed", date=date, status="closed"),
            slot(_id="cancelled", date=date, status="cancelled"),
        ])

        result = await list_available_slots(db, sport="Badminton", date=date, campus="RR")

        self.assertEqual([item["_id"] for item in result], ["open"])

    async def test_facility_fields_and_venue_fallback_are_serialized(self):
        item = serialize_student_slot(slot(venue=None))

        self.assertEqual(item["facility_id"], "facility-1")
        self.assertEqual(item["facility_name"], "Badminton Court 1")
        self.assertEqual(item["venue"], "Badminton Court 1")
        self.assertEqual(item["duration_minutes"], 60)
        self.assertEqual(item["slot_type"], "generated")
        self.assertFalse(item["is_manual"])

    async def test_participant_information_is_not_exposed(self):
        item = serialize_student_slot(slot(
            participants=[{"srn": "PES123"}],
            user_snapshot={"phone": "9999999999"},
            leader_user_id="user-1",
        ))

        forbidden = {"participants", "user_snapshot", "leader_user_id", "name", "srn", "phone", "branch", "program", "semester", "section"}
        self.assertFalse(forbidden & set(item))

    async def test_old_non_facility_slots_do_not_crash(self):
        legacy = slot(facility_id=None, facility_name=None, venue="Legacy Venue")
        item = serialize_student_slot(legacy)

        self.assertIsNone(item["facility_id"])
        self.assertIsNone(item["facility_name"])
        self.assertEqual(item["venue"], "Legacy Venue")


if __name__ == "__main__":
    unittest.main()
