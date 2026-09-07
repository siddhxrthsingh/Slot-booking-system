import unittest
from datetime import datetime, timedelta, timezone

from app.services.booking_service import list_available_slots, serialize_student_slot


class FakeUpdateResult:
    def __init__(self, inserted):
        self.upserted_id = "new-id" if inserted else None


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

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if matches(doc, query):
                return FakeUpdateResult(False)
        if upsert:
            self.docs.append(dict(update["$setOnInsert"]))
            return FakeUpdateResult(True)
        return FakeUpdateResult(False)


class FakeDb:
    def __init__(self, slots, facilities=None, templates=None):
        self.collections = {
            "slots": FakeCollection(slots),
            "facilities": FakeCollection(facilities or []),
            "schedule_templates": FakeCollection(templates or []),
        }

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


def future_weekday():
    d = future_date()
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _student_period(start, end):
    return {
        "start_time": start,
        "end_time": end,
        "period_type": "student",
        "duration_minutes": 60,
        "is_bookable": True,
    }


class AutomaticGenerationOnRetrievalTests(unittest.IsolatedAsyncioTestCase):
    """Requesting available slots for a date with no generated slots yet must
    trigger generate_slots_for_date() before the query runs."""

    def _weekday_db(self):
        facilities = [
            {
                "_id": "badminton-1", "campus": "RR", "sport": "Badminton",
                "name": "Court 1", "display_name": "Badminton Court 1",
                "capacity": 6, "is_active": True, "sort_order": 1,
            },
        ]
        templates = [
            {
                "campus": "RR", "sport": "Badminton", "facility_scope": "sport",
                "day_type": "weekday",
                "periods": [_student_period("09:00", "10:00"), _student_period("10:00", "11:00")],
                "is_active": True, "priority": 10, "updated_at": datetime(2026, 1, 1),
            },
        ]
        return FakeDb([], facilities=facilities, templates=templates)

    async def test_requesting_slots_for_date_generates_them_first(self):
        weekday_date = future_weekday()
        db = self._weekday_db()

        self.assertEqual(db["slots"].docs, [])

        result = await list_available_slots(db, sport="Badminton", date=weekday_date, campus="RR")

        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)
        self.assertEqual({item["start_time"] for item in result}, {"09:00", "10:00"})

    async def test_generation_trigger_is_idempotent_on_repeat_requests(self):
        weekday_date = future_weekday()
        db = self._weekday_db()

        first = await list_available_slots(db, sport="Badminton", date=weekday_date, campus="RR")
        second = await list_available_slots(db, sport="Badminton", date=weekday_date, campus="RR")

        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertEqual(
            len([s for s in db["slots"].docs if s.get("slot_type") == "generated"]), 2
        )

    async def test_existing_generated_slot_state_is_preserved_across_retrieval(self):
        weekday_date = future_weekday()
        db = self._weekday_db()
        db["slots"].docs.append(slot(
            _id="existing", date=weekday_date, start_time="09:00", end_time="10:00",
            facility_id="badminton-1", facility_name="Badminton Court 1",
            booked_count=3, status="open",
        ))

        result = await list_available_slots(db, sport="Badminton", date=weekday_date, campus="RR")

        existing = next(item for item in result if item["_id"] == "existing")
        self.assertEqual(existing["booked_count"], 3)
        # only the missing 10:00 slot should have been newly generated
        generated_count = len([s for s in db["slots"].docs if s.get("slot_type") == "generated"])
        self.assertEqual(generated_count, 2)

    async def test_manual_slots_are_untouched_by_generation_trigger(self):
        weekday_date = future_weekday()
        db = self._weekday_db()
        db["slots"].docs.append(slot(
            _id="manual-1", date=weekday_date, start_time="09:00", end_time="10:30",
            facility_id="badminton-1", facility_name="Badminton Court 1",
            slot_type="manual", is_manual=True, duration_minutes=90,
        ))

        result = await list_available_slots(db, sport="Badminton", date=weekday_date, campus="RR")

        manual_ids = [item["_id"] for item in result if item.get("is_manual")]
        self.assertIn("manual-1", manual_ids)
        manual_doc = next(s for s in db["slots"].docs if s["_id"] == "manual-1")
        self.assertEqual(manual_doc["start_time"], "09:00")
        self.assertEqual(manual_doc["end_time"], "10:30")

    async def test_no_date_requested_does_not_trigger_generation(self):
        db = self._weekday_db()

        await list_available_slots(db, sport="Badminton", campus="RR")

        self.assertEqual(db["slots"].docs, [])

    async def test_requesting_todays_date_generates_todays_slots(self):
        """Dashboard now explicitly requests today's date; this must trigger
        generation for today the same way it already does for other dates."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        while today.weekday() >= 5:
            today += timedelta(days=1)
        db = self._weekday_db()

        await list_available_slots(db, sport="Badminton", date=today, campus="RR")

        # Generation itself must happen for today regardless of what time of
        # day the test runs at; whether an individual period is still visible
        # in the result once generated is covered separately by
        # PastSlotVisibilityTests (a period already elapsed today is
        # correctly filtered out of student-facing results).
        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)
        self.assertTrue(all(s["date"] == today for s in generated))

    async def test_requesting_tomorrows_date_generates_tomorrows_slots(self):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        while tomorrow.weekday() >= 5:
            tomorrow += timedelta(days=1)
        db = self._weekday_db()

        result = await list_available_slots(db, sport="Badminton", date=tomorrow, campus="RR")

        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)
        self.assertTrue(all(s["date"] == tomorrow for s in generated))
        self.assertEqual(len(result), 2)


class PastSlotVisibilityTests(unittest.IsolatedAsyncioTestCase):
    """Student-facing retrieval must never surface a slot whose end time has
    already elapsed, without deleting the underlying document."""

    async def test_slot_that_already_ended_today_is_excluded(self):
        now = datetime.now(timezone.utc)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_end = now - timedelta(minutes=5)
        db = FakeDb([
            slot(
                _id="elapsed",
                date=today_midnight,
                start_time=(elapsed_end - timedelta(hours=1)).strftime("%H:%M"),
                end_time=elapsed_end.strftime("%H:%M"),
            ),
        ])

        result = await list_available_slots(db, sport="Badminton", date=today_midnight, campus="RR")

        self.assertEqual(result, [])
        # The document itself must still exist — not deleted.
        self.assertEqual(len(db["slots"].docs), 1)

    async def test_slot_still_in_progress_or_upcoming_today_is_included(self):
        now = datetime.now(timezone.utc)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        future_end = now + timedelta(hours=1)
        db = FakeDb([
            slot(
                _id="upcoming",
                date=today_midnight,
                start_time=now.strftime("%H:%M"),
                end_time=future_end.strftime("%H:%M"),
            ),
        ])

        result = await list_available_slots(db, sport="Badminton", date=today_midnight, campus="RR")

        self.assertEqual([item["_id"] for item in result], ["upcoming"])

    async def test_tomorrows_slots_remain_visible(self):
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        db = FakeDb([slot(_id="tomorrow-slot", date=tomorrow)])

        result = await list_available_slots(db, sport="Badminton", date=tomorrow, campus="RR")

        self.assertEqual([item["_id"] for item in result], ["tomorrow-slot"])


if __name__ == "__main__":
    unittest.main()
