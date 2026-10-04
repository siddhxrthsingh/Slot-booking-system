"""
Free Speed Plan Step 3: student-facing slot generation must not block the
request. ensure_slots_generated(background=True) (used by list_available_slots)
starts/reuses a tracked asyncio.Task and returns immediately when slots are
missing; ensure_slots_generated(background=False) (the admin default,
unchanged) still awaits generation synchronously so RC-4 diagnostics stay
accurate for the request that triggered them.
"""
import asyncio
import unittest
from datetime import datetime, timedelta

from app.services import booking_service
from app.services.booking_service import ensure_slots_generated, wait_for_background_generation
from tests.test_facility_slot_retrieval import FakeDb, _student_period, future_weekday


def _weekday_db():
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


class SlotGenerationBackgroundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        # Don't leak in-flight/completed task entries into other test modules.
        booking_service._generation_tasks.clear()

    # A. Existing slots return without any generation work being started.
    async def test_existing_slots_return_without_generation_work(self):
        weekday_date = future_weekday()
        db = _weekday_db()
        db["slots"].docs.append({
            "_id": "existing", "campus": "RR", "facility_id": "badminton-1",
            "facility_name": "Badminton Court 1", "sport": "Badminton",
            "date": weekday_date, "start_time": "09:00", "end_time": "10:00",
            "slot_type": "generated", "capacity": 6, "booked_count": 0,
            "status": "open",
        })

        result = await ensure_slots_generated(db, weekday_date, campus="RR", background=True)

        self.assertIsNone(result)
        self.assertEqual(len(booking_service._generation_tasks), 0)

    # B. Generation can be triggered without blocking the normal response.
    async def test_background_mode_returns_immediately_without_awaiting_generation(self):
        weekday_date = future_weekday()
        db = _weekday_db()

        result = await ensure_slots_generated(db, weekday_date, campus="RR", background=True)

        # Returns immediately with no summary — the caller is never blocked
        # on generation actually finishing.
        self.assertIsNone(result)
        # A task was started but the facilities scan has not necessarily run
        # yet (nothing awaited it inside this call).
        self.assertEqual(len(db["slots"].docs), 0)

        await wait_for_background_generation()
        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)

    # C. Two simultaneous (concurrent) student requests for the same
    # campus/date do not create duplicate slot records, and share one
    # generation task rather than each starting their own.
    async def test_concurrent_requests_do_not_duplicate_generation(self):
        weekday_date = future_weekday()
        db = _weekday_db()
        original_find = db["facilities"].find
        call_count = {"n": 0}

        def counting_find(query):
            call_count["n"] += 1
            return original_find(query)

        db["facilities"].find = counting_find

        await asyncio.gather(
            ensure_slots_generated(db, weekday_date, campus="RR", background=True),
            ensure_slots_generated(db, weekday_date, campus="RR", background=True),
        )
        await wait_for_background_generation()

        # Both concurrent callers shared one generation pass, not two.
        self.assertEqual(call_count["n"], 1)
        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)

    # D. Missing slots still eventually become available (eventual
    # consistency — the request that triggers generation may not see it
    # finished, but a subsequent request does).
    async def test_missing_slots_eventually_become_available(self):
        weekday_date = future_weekday()
        db = _weekday_db()

        await ensure_slots_generated(db, weekday_date, campus="RR", background=True)
        self.assertEqual(len(db["slots"].docs), 0)  # not yet — still in flight

        await wait_for_background_generation()

        second = await ensure_slots_generated(db, weekday_date, campus="RR", background=True)
        self.assertIsNone(second)  # already generated — fast path now
        generated = [s for s in db["slots"].docs if s.get("slot_type") == "generated"]
        self.assertEqual(len(generated), 2)

    # E. RC-4 diagnostics remain correct: the admin (foreground/default)
    # path still gets the full summary synchronously, even when a student
    # request already has a background generation in flight for the same
    # campus/date — the admin call reuses and awaits that same task.
    async def test_admin_foreground_call_still_gets_full_diagnostics(self):
        weekday_date = future_weekday()
        db = _weekday_db()
        db["facilities"].docs.append({
            "_id": "basketball-1", "campus": "RR", "sport": "Basketball",
            "name": "Court 1", "display_name": "Basketball Court 1",
            "capacity": 12, "is_active": True, "sort_order": 1,
        })

        # Student request kicks off generation in the background...
        await ensure_slots_generated(db, weekday_date, campus="RR", background=True)
        # ...admin request for the same date must still get the synchronous,
        # fully-populated diagnostics summary (basketball has no template).
        summary = await ensure_slots_generated(db, weekday_date, campus="RR", background=False)

        self.assertIsNotNone(summary)
        self.assertEqual(summary["facilities_processed"], 2)
        self.assertTrue(any(e["facility_id"] == "basketball-1" for e in summary["errors"]))

    # F. No booking behavior changes: a slot produced via the background
    # generation path is identical in shape/state to one produced
    # synchronously — booking logic itself was never touched by this step.
    async def test_background_generated_slot_is_open_and_bookable_shaped(self):
        weekday_date = future_weekday()
        db = _weekday_db()

        await ensure_slots_generated(db, weekday_date, campus="RR", background=True)
        await wait_for_background_generation()

        slot = next(s for s in db["slots"].docs if s.get("slot_type") == "generated")
        self.assertEqual(slot["status"], "open")
        self.assertEqual(slot["booked_count"], 0)
        self.assertEqual(slot["capacity"], 6)
        self.assertIsNone(slot["leader_user_id"])


if __name__ == "__main__":
    unittest.main()
