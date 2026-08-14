import unittest
from datetime import datetime

from app.services.slot_generation_service import generate_slots_for_date


def period(start, end, period_type):
    return {
        "start_time": start,
        "end_time": end,
        "period_type": period_type,
        "duration_minutes": 60,
        "is_bookable": period_type == "student",
    }


INDOOR_WEEKDAY = [
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

BADMINTON_COURT_1_WEEKDAY = [
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

INDOOR_SATURDAY = [
    period("06:00", "07:00", "student"),
    period("07:00", "08:00", "student"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
    period("10:00", "11:00", "student"),
    period("11:00", "12:00", "student"),
    period("12:00", "13:00", "student"),
]

BADMINTON_COURT_1_SATURDAY = [
    period("06:00", "07:00", "staff"),
    period("07:00", "08:00", "staff"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
    period("10:00", "11:00", "student"),
    period("11:00", "12:00", "student"),
    period("12:00", "13:00", "student"),
]

INDOOR_SUNDAY = [
    period("06:00", "07:00", "student"),
    period("07:00", "08:00", "student"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
]

BADMINTON_COURT_1_SUNDAY = [
    period("06:00", "07:00", "staff"),
    period("07:00", "08:00", "staff"),
    period("08:00", "09:00", "cleaning"),
    period("09:00", "10:00", "student"),
]

COURT_WEEKDAY = [
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


class FakeUpdateResult:
    def __init__(self, inserted):
        self.upserted_id = "new-id" if inserted else None


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, sort_spec):
        for key, direction in reversed(sort_spec):
            self.docs.sort(key=lambda doc: doc.get(key), reverse=direction < 0)
        return self

    async def to_list(self, length):
        return self.docs[:length]


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

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
    def __init__(self, facilities, templates, slots=None):
        self.collections = {
            "facilities": FakeCollection(facilities),
            "schedule_templates": FakeCollection(templates),
            "slots": FakeCollection(slots),
        }

    def __getitem__(self, name):
        return self.collections[name]


def matches(doc, query):
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            continue
        if actual != expected:
            return False
    return True


def sport_template(sport, day_type, periods):
    return {
        "campus": "RR",
        "sport": sport,
        "facility_scope": "sport",
        "day_type": day_type,
        "periods": periods,
        "is_active": True,
        "priority": 10,
        "updated_at": datetime(2026, 1, 1),
    }


def facility_template(facility_id, day_type, periods):
    return {
        "campus": "RR",
        "sport": "Badminton",
        "facility_scope": "facility",
        "facility_id": facility_id,
        "facility_name": "Badminton Court 1",
        "day_type": day_type,
        "periods": periods,
        "is_active": True,
        "priority": 100,
        "updated_at": datetime(2026, 1, 1),
    }


def default_db(extra_slots=None, omit_templates=()):
    facilities = [
        {"_id": "badminton-1", "campus": "RR", "sport": "Badminton", "name": "Court 1", "display_name": "Badminton Court 1", "capacity": 6, "is_active": True, "sort_order": 1},
        {"_id": "badminton-2", "campus": "RR", "sport": "Badminton", "name": "Court 2", "display_name": "Badminton Court 2", "capacity": 6, "is_active": True, "sort_order": 2},
        {"_id": "basketball-1", "campus": "RR", "sport": "Basketball", "name": "Court 1", "display_name": "Basketball Court 1", "capacity": 12, "is_active": True, "sort_order": 1},
    ]
    templates = [
        sport_template("Badminton", "weekday", INDOOR_WEEKDAY),
        sport_template("Badminton", "saturday", INDOOR_SATURDAY),
        sport_template("Badminton", "sunday", INDOOR_SUNDAY),
        facility_template("badminton-1", "weekday", BADMINTON_COURT_1_WEEKDAY),
        facility_template("badminton-1", "saturday", BADMINTON_COURT_1_SATURDAY),
        facility_template("badminton-1", "sunday", BADMINTON_COURT_1_SUNDAY),
        sport_template("Basketball", "weekday", COURT_WEEKDAY),
    ]
    templates = [template for template in templates if (template["sport"], template["day_type"]) not in omit_templates]
    return FakeDb(facilities, templates, extra_slots or [])


def slots_for(db, facility_id):
    return [
        slot for slot in db["slots"].docs
        if slot.get("facility_id") == facility_id and slot.get("slot_type") == "generated"
    ]


class SlotGenerationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_weekday_expected_counts(self):
        db = default_db()
        result = await generate_slots_for_date(db, datetime(2026, 8, 17))

        self.assertEqual(result["day_type"], "weekday")
        self.assertEqual(len(slots_for(db, "badminton-1")), 6)
        self.assertEqual(len(slots_for(db, "badminton-2")), 11)
        self.assertEqual(len(slots_for(db, "basketball-1")), 9)

    async def test_saturday_expected_counts(self):
        db = default_db()
        await generate_slots_for_date(db, datetime(2026, 8, 22))

        self.assertEqual(len(slots_for(db, "badminton-1")), 4)
        self.assertEqual(len(slots_for(db, "badminton-2")), 6)

    async def test_sunday_expected_counts_and_missing_basketball_template(self):
        db = default_db()
        result = await generate_slots_for_date(db, datetime(2026, 8, 23))

        self.assertEqual(len(slots_for(db, "badminton-1")), 1)
        self.assertEqual(len(slots_for(db, "badminton-2")), 3)
        self.assertEqual(len(slots_for(db, "basketball-1")), 0)
        self.assertTrue(any(error["reason"] == "no_applicable_template" for error in result["errors"]))

    async def test_second_run_creates_no_duplicates(self):
        db = default_db()
        first = await generate_slots_for_date(db, datetime(2026, 8, 17))
        second = await generate_slots_for_date(db, datetime(2026, 8, 17))

        self.assertEqual(first["slots_created"], 26)
        self.assertEqual(second["slots_created"], 0)
        self.assertEqual(second["slots_existing"], 26)
        self.assertEqual(len(db["slots"].docs), 26)

    async def test_existing_booked_generated_slot_is_not_reset(self):
        existing = {
            "campus": "RR",
            "facility_id": "badminton-1",
            "date": datetime(2026, 8, 17),
            "start_time": "09:00",
            "end_time": "10:00",
            "slot_type": "generated",
            "sport": "Badminton",
            "booked_count": 3,
            "status": "full",
            "leader_user_id": "user-1",
        }
        db = default_db([existing])
        await generate_slots_for_date(db, datetime(2026, 8, 17))

        self.assertEqual(existing["booked_count"], 3)
        self.assertEqual(existing["status"], "full")
        self.assertEqual(existing["leader_user_id"], "user-1")

    async def test_existing_manual_slot_is_not_modified_and_overlap_is_reported(self):
        manual = {
            "_id": "manual-1",
            "campus": "RR",
            "facility_id": "badminton-1",
            "date": datetime(2026, 8, 17),
            "start_time": "09:30",
            "end_time": "10:30",
            "slot_type": "manual",
            "is_manual": True,
            "notes": "Manual slot",
        }
        db = default_db([manual])
        result = await generate_slots_for_date(db, datetime(2026, 8, 17))

        self.assertIn(manual, db["slots"].docs)
        self.assertEqual(manual["notes"], "Manual slot")
        self.assertGreaterEqual(len(result["manual_overlaps"]), 1)

    async def test_no_cleaning_lunch_or_staff_slots_are_created(self):
        db = default_db()
        await generate_slots_for_date(db, datetime(2026, 8, 17))

        self.assertTrue(all(slot["slot_type"] == "generated" for slot in db["slots"].docs))
        self.assertFalse(any(slot["start_time"] == "08:00" for slot in db["slots"].docs))
        self.assertFalse(any(slot["start_time"] == "13:00" for slot in db["slots"].docs))

    async def test_all_generated_slots_have_sixty_minute_duration(self):
        db = default_db()
        await generate_slots_for_date(db, datetime(2026, 8, 17))

        self.assertTrue(all(slot["duration_minutes"] == 60 for slot in db["slots"].docs))

    async def test_invalid_student_period_is_skipped(self):
        db = default_db()
        db["schedule_templates"].docs.append({
            "campus": "RR",
            "sport": "Basketball",
            "facility_scope": "facility",
            "facility_id": "basketball-1",
            "day_type": "weekday",
            "periods": [{
                "start_time": "09:00",
                "end_time": "10:30",
                "period_type": "student",
                "duration_minutes": 90,
                "is_bookable": True,
            }],
            "is_active": True,
            "priority": 100,
            "updated_at": datetime(2026, 1, 2),
        })
        result = await generate_slots_for_date(db, datetime(2026, 8, 17))

        self.assertEqual(len(slots_for(db, "basketball-1")), 0)
        self.assertTrue(any(error["reason"] == "invalid_student_period_duration" for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
