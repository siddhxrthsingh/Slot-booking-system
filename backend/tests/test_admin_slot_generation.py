import unittest
from datetime import datetime, timedelta, timezone

from app.services.admin_service import list_all_slots
from app.services.booking_service import list_available_slots
from tests.test_facility_slot_retrieval import FakeDb, _student_period, future_weekday


class AdminSlotGenerationTests(unittest.IsolatedAsyncioTestCase):
    """RC-1: the admin Slots page must not depend on a student having opened
    the dashboard first — list_all_slots must ensure generation itself when
    a date is requested, reusing generate_slots_for_date()."""

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

    # A. Admin opens Slots before any student has generated slots.
    async def test_admin_request_generates_slots_when_none_exist(self):
        weekday_date = future_weekday()
        db = self._weekday_db()

        self.assertEqual(db["slots"].docs, [])

        result = await list_all_slots(db, campus="RR", date=weekday_date.date())

        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)
        self.assertEqual({s["start_time"] for s in result["items"]}, {"09:00", "10:00"})
        self.assertEqual(result["total"], 2)

    # B. Student never opened the dashboard; admin still gets slots. Same
    # assertion as A — list_all_slots is the only entrypoint exercised.
    async def test_admin_gets_slots_without_any_student_visit(self):
        weekday_date = future_weekday()
        db = self._weekday_db()

        result = await list_all_slots(db, campus="RR", date=weekday_date.date())

        self.assertEqual(len(result["items"]), 2)

    # C/D/E: today / tomorrow / day-after-tomorrow requests each generate and
    # return only that date's slots.
    async def test_admin_requests_are_scoped_to_the_requested_date(self):
        db = self._weekday_db()
        d0 = future_weekday()
        d1 = d0 + timedelta(days=1)
        while d1.weekday() >= 5:
            d1 += timedelta(days=1)

        result0 = await list_all_slots(db, campus="RR", date=d0.date())
        result1 = await list_all_slots(db, campus="RR", date=d1.date())

        self.assertTrue(all(s["date"] == d0 for s in result0["items"]))
        self.assertTrue(all(s["date"] == d1 for s in result1["items"]))
        self.assertEqual(len(result0["items"]), 2)
        self.assertEqual(len(result1["items"]), 2)

    # F. Repeated admin requests create no duplicate slots.
    async def test_repeated_admin_requests_do_not_duplicate_slots(self):
        weekday_date = future_weekday()
        db = self._weekday_db()

        await list_all_slots(db, campus="RR", date=weekday_date.date())
        await list_all_slots(db, campus="RR", date=weekday_date.date())

        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)

    # G. Student request followed by admin request: no duplicates.
    async def test_student_then_admin_request_does_not_duplicate(self):
        weekday_date = future_weekday()
        db = self._weekday_db()

        await list_available_slots(db, sport="Badminton", date=weekday_date, campus="RR")
        await list_all_slots(db, campus="RR", date=weekday_date.date())

        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)

    # H. Admin request followed by student request: no duplicates.
    async def test_admin_then_student_request_does_not_duplicate(self):
        weekday_date = future_weekday()
        db = self._weekday_db()

        await list_all_slots(db, campus="RR", date=weekday_date.date())
        await list_available_slots(db, sport="Badminton", date=weekday_date, campus="RR")

        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)

    # Existing manual slots are not overwritten.
    async def test_manual_slot_is_untouched_by_admin_generation_trigger(self):
        weekday_date = future_weekday()
        db = self._weekday_db()
        manual = {
            "_id": "manual-1", "facility_id": "badminton-1",
            "facility_name": "Badminton Court 1", "sport": "Badminton",
            "date": weekday_date, "start_time": "20:00", "end_time": "21:00",
            "venue": "Badminton Court 1", "campus": "RR", "capacity": 6,
            "duration_minutes": 60, "slot_type": "manual", "is_manual": True,
            "leader_user_id": None, "booked_count": 2, "status": "open",
        }
        db["slots"].docs.append(manual)

        await list_all_slots(db, campus="RR", date=weekday_date.date())

        stored_manual = next(s for s in db["slots"].docs if s["_id"] == "manual-1")
        self.assertEqual(stored_manual["booked_count"], 2)
        self.assertEqual(stored_manual["start_time"], "20:00")

    # No date given: behaves as before (no generation attempt, all slots).
    async def test_no_date_given_skips_generation_entirely(self):
        db = self._weekday_db()

        result = await list_all_slots(db, campus="RR")

        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)
        self.assertEqual(db["slots"].docs, [])


if __name__ == "__main__":
    unittest.main()
