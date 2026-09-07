import unittest
from datetime import datetime, timezone

from app.utils import IST, ensure_utc
from app.services.admin_service import get_slot_roster
from app.services.booking_service import (
    _slot_end_dt,
    _slot_start_dt,
    create_booking,
    serialize_student_slot,
)
from tests.test_booking_join_service import FakeDb, make_facility, make_slot, make_user


class EnsureUtcTests(unittest.TestCase):
    def test_naive_datetime_gets_utc_tzinfo(self):
        naive = datetime(2026, 9, 7, 12, 31, 0)
        result = ensure_utc(naive)
        self.assertEqual(result.tzinfo, timezone.utc)
        self.assertEqual(result.hour, 12)

    def test_aware_datetime_is_left_unchanged(self):
        aware = datetime(2026, 9, 7, 12, 31, 0, tzinfo=timezone.utc)
        self.assertEqual(ensure_utc(aware), aware)

    def test_none_passes_through(self):
        self.assertIsNone(ensure_utc(None))

    def test_known_utc_instant_converts_to_correct_ist_display_time(self):
        # 12:31 UTC == 18:01 IST (UTC+5:30) on the same calendar day.
        naive_from_mongo = datetime(2026, 9, 7, 12, 31, 0)
        ist_time = ensure_utc(naive_from_mongo).astimezone(IST)
        self.assertEqual((ist_time.hour, ist_time.minute), (18, 1))
        self.assertEqual(ist_time.day, 7)

    def test_utc_instant_crossing_midnight_shows_correct_ist_calendar_day(self):
        # 20:00 UTC on the 7th == 01:30 IST on the 8th.
        naive_from_mongo = datetime(2026, 9, 7, 20, 0, 0)
        ist_time = ensure_utc(naive_from_mongo).astimezone(IST)
        self.assertEqual(ist_time.day, 8)
        self.assertEqual((ist_time.hour, ist_time.minute), (1, 30))


class RosterTimestampTests(unittest.IsolatedAsyncioTestCase):
    async def test_roster_joined_at_is_tz_aware_even_when_stored_naive(self):
        """Real MongoDB returns naive datetimes for stored UTC instants.
        The roster response must attach UTC tzinfo so the frontend doesn't
        misinterpret the instant as browser-local time."""
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        # Simulate MongoDB stripping tzinfo on write/read.
        stored = next(b for b in db["bookings"].docs if b["_id"] == booking["_id"])
        stored["joined_at"] = stored["joined_at"].replace(tzinfo=None)

        roster = await get_slot_roster(db, str(slot["_id"]))
        entry = roster["participants"][0]

        self.assertIsNotNone(entry["joined_at"].tzinfo)
        self.assertEqual(entry["joined_at"].tzinfo, timezone.utc)

    async def test_create_booking_stores_correct_utc_instant(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        before = datetime.now(timezone.utc)
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))
        after = datetime.now(timezone.utc)

        joined_at = ensure_utc(booking["joined_at"])
        self.assertLessEqual(before, joined_at)
        self.assertLessEqual(joined_at, after)


class SlotDateAsStringTests(unittest.TestCase):
    """Regression test: a small number of pre-existing slot documents have
    `date` stored as an ISO string (e.g. "2026-09-07T00:00:00.000Z") instead
    of a datetime. Before this fix, _slot_start_dt/_slot_end_dt crashed with
    AttributeError on these records, which took down /admin/slots,
    /admin/metrics and any listing that filters slots by their end time."""

    def _string_date_slot(self):
        return make_slot(date="2026-09-07T00:00:00.000Z")

    def test_slot_start_dt_handles_string_date(self):
        slot = self._string_date_slot()
        start = _slot_start_dt(slot)
        self.assertEqual(start.tzinfo, timezone.utc)

    def test_slot_end_dt_handles_string_date(self):
        slot = self._string_date_slot()
        end = _slot_end_dt(slot)
        self.assertEqual(end.tzinfo, timezone.utc)
        self.assertGreater(end, _slot_start_dt(slot))

    def test_serialize_student_slot_handles_string_date(self):
        slot = self._string_date_slot()
        serialized = serialize_student_slot(slot)
        self.assertEqual(serialized["date"].tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
