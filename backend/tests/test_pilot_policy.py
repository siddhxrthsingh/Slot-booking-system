"""Pilot policy: capacity 6->4 (12 unchanged) and ONE booking per student per day."""
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.services.booking_service import DAILY_LIMIT_MESSAGE, cancel_booking, create_booking
from migrate_slot_capacity import migrate_slot_capacity
from seed_facilities import RR_FACILITIES
from tests.test_booking_join_service import (
    FakeDb, future_date, make_facility, make_slot, make_user,
)


class CapacityTests(unittest.IsolatedAsyncioTestCase):
    def test_seed_capacities(self):
        for f in RR_FACILITIES:
            expected = 12 if f["sport"] in ("Basketball", "Volleyball") else 4
            self.assertEqual(f["capacity"], expected, f["display_name"])

    async def test_old_capacity_6_slot_accepts_only_4(self):
        slot = make_slot(capacity=6)  # stale slot doc; facility is authoritative
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 4)])
        for _ in range(4):
            await create_booking(db, user=make_user(), slot_id=str(slot["_id"]))
        self.assertEqual(db["slots"].docs[0]["status"], "full")
        with self.assertRaises((ValueError, LookupError)):
            await create_booking(db, user=make_user(), slot_id=str(slot["_id"]))
        self.assertEqual(db["slots"].docs[0]["booked_count"], 4)

    async def test_capacity_12_still_accepts_12(self):
        slot = make_slot(sport="Basketball", capacity=12)
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 12)])
        for _ in range(12):
            await create_booking(db, user=make_user(), slot_id=str(slot["_id"]))
        self.assertEqual(db["slots"].docs[0]["booked_count"], 12)
        with self.assertRaises((ValueError, LookupError)):
            await create_booking(db, user=make_user(), slot_id=str(slot["_id"]))

    async def test_concurrent_joins_cannot_exceed_4(self):
        slot = make_slot(capacity=4)
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 4)])
        results = await asyncio.gather(
            *[create_booking(db, user=make_user(), slot_id=str(slot["_id"])) for _ in range(8)],
            return_exceptions=True,
        )
        self.assertEqual(len([r for r in results if not isinstance(r, Exception)]), 4)
        self.assertEqual(db["slots"].docs[0]["booked_count"], 4)


class OneBookingPerDayTests(unittest.IsolatedAsyncioTestCase):
    def _db(self, *slots):
        return FakeDb(slots=list(slots), facilities=[make_facility(s, 4) for s in slots])

    async def test_same_day_other_sport_other_time_and_same_sport_rejected(self):
        d = future_date()
        bad1 = make_slot(date=d, sport="Badminton", start_time="06:00", end_time="07:00")
        tt = make_slot(date=d, sport="Table Tennis", start_time="08:00", end_time="09:00")
        bad2 = make_slot(date=d, sport="Badminton", start_time="14:00", end_time="15:00")
        adj = make_slot(date=d, sport="Badminton", start_time="07:00", end_time="08:00")
        db = self._db(bad1, tt, bad2, adj)
        user = make_user()
        await create_booking(db, user=user, slot_id=str(bad1["_id"]))
        for other in (tt, bad2, adj):
            with self.assertRaises(ValueError) as ctx:
                await create_booking(db, user=user, slot_id=str(other["_id"]))
            self.assertEqual(str(ctx.exception), DAILY_LIMIT_MESSAGE)
            self.assertEqual(other["booked_count"], 0)

    async def test_next_day_allowed(self):
        s1 = make_slot(date=future_date(3))
        s2 = make_slot(date=future_date(4))
        db = self._db(s1, s2)
        user = make_user()
        await create_booking(db, user=user, slot_id=str(s1["_id"]))
        await create_booking(db, user=user, slot_id=str(s2["_id"]))

    async def test_simultaneous_requests_different_slots_only_one_succeeds(self):
        d = future_date()
        s1 = make_slot(date=d, start_time="09:00", end_time="10:00")
        s2 = make_slot(date=d, sport="Squash", start_time="11:00", end_time="12:00")
        db = self._db(s1, s2)
        user = make_user()
        results = await asyncio.gather(
            create_booking(db, user=user, slot_id=str(s1["_id"])),
            create_booking(db, user=user, slot_id=str(s2["_id"])),
            return_exceptions=True,
        )
        ok = [r for r in results if not isinstance(r, Exception)]
        bad = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(len(ok), 1)
        self.assertEqual(len(bad), 1)
        self.assertEqual(str(bad[0]), DAILY_LIMIT_MESSAGE)
        active = [b for b in db["bookings"].docs if b["status"] != "cancelled"]
        self.assertEqual(len(active), 1)
        # Loser's seat was released and it left no leader behind.
        self.assertEqual(sorted(s["booked_count"] for s in db["slots"].docs), [0, 1])
        loser = next(s for s in db["slots"].docs if s["booked_count"] == 0)
        self.assertIsNone(loser["leader_user_id"])

    async def test_different_students_can_share_a_slot(self):
        s = make_slot()
        db = self._db(s)
        for _ in range(3):
            await create_booking(db, user=make_user(), slot_id=str(s["_id"]))
        self.assertEqual(db["slots"].docs[0]["booked_count"], 3)

    async def test_legacy_multiple_bookings_kept_and_block_new_ones(self):
        d = future_date()
        s1 = make_slot(date=d, start_time="06:00", end_time="07:00", booked_count=1)
        s2 = make_slot(date=d, start_time="09:00", end_time="10:00", booked_count=1)
        s3 = make_slot(date=d, start_time="14:00", end_time="15:00")
        db = self._db(s1, s2, s3)
        user = make_user()
        legacy = [
            {"_id": ObjectId(), "user_id": user["_id"], "slot_id": s["_id"],
             "sport": "Badminton", "status": "confirmed"}  # no active_day_key
            for s in (s1, s2)
        ]
        for b in legacy:
            await db["bookings"].insert_one(b)
        before = [dict(b) for b in db["bookings"].docs]
        with self.assertRaises(ValueError) as ctx:
            await create_booking(db, user=user, slot_id=str(s3["_id"]))
        self.assertEqual(str(ctx.exception), DAILY_LIMIT_MESSAGE)
        self.assertEqual(db["bookings"].docs, before)  # untouched, none removed
        self.assertEqual((s1["booked_count"], s2["booked_count"], s3["booked_count"]), (1, 1, 0))

    async def test_fifth_student_rejected_at_capacity_4(self):
        slot = make_slot(capacity=6)
        db = self._db(slot)
        for _ in range(4):
            await create_booking(db, user=make_user(_id=ObjectId()), slot_id=str(slot["_id"]))
        with self.assertRaises((ValueError, LookupError)):  # slot is now "full"
            await create_booking(db, user=make_user(_id=ObjectId()), slot_id=str(slot["_id"]))
        self.assertEqual(slot["booked_count"], 4)

    async def test_early_cancel_frees_the_day_and_keeps_history(self):
        d = future_date()
        s1 = make_slot(date=d, start_time="09:00", end_time="10:00")
        s2 = make_slot(date=d, sport="Squash", start_time="11:00", end_time="12:00")
        db = self._db(s1, s2)
        user = make_user()
        b = await create_booking(db, user=user, slot_id=str(s1["_id"]))
        await cancel_booking(db, str(b["_id"]), str(user["_id"]))
        cancelled = db["bookings"].docs[0]
        self.assertEqual(cancelled["status"], "cancelled")  # not deleted
        self.assertNotIn("active_day_key", cancelled)
        await create_booking(db, user=user, slot_id=str(s2["_id"]))  # day freed

    async def test_late_cancel_still_bans(self):
        ist = (datetime.now(timezone.utc) + timedelta(hours=1)).astimezone(ZoneInfo("Asia/Kolkata"))
        s1 = make_slot(
            date=ist.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc),
            start_time=ist.strftime("%H:%M"),
            end_time=(ist + timedelta(hours=1)).strftime("%H:%M"),
        )
        db = self._db(s1)
        user = make_user()
        b = await create_booking(db, user=user, slot_id=str(s1["_id"]))
        await cancel_booking(db, str(b["_id"]), str(user["_id"]))
        self.assertEqual(len(db["bans"].docs), 1)
        with self.assertRaises(ValueError):
            await create_booking(db, user=user, slot_id=str(s1["_id"]))


def _ne_find(coll):
    """FakeCollection.matches has no $ne-on-capacity support for this query shape."""
    orig = coll.find

    def find(query=None, projection=None):
        query = dict(query or {})
        ne = query.pop("capacity", None)
        cur = orig(query)
        if ne and "$ne" in ne:
            cur.docs = [d for d in cur.docs if d.get("capacity") != ne["$ne"]]
        return cur
    return find


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_apply_and_flagging(self):
        fac = {"_id": ObjectId(), "capacity": 4, "display_name": "Badminton Court 1"}

        def mk(**kw):
            return make_slot(facility_id=fac["_id"], capacity=6, **kw)

        ok = mk(booked_count=2)
        at4 = mk(booked_count=4, status="full")
        over = mk(booked_count=5, status="full")
        past = mk(date=future_date(-3), booked_count=1)
        cancelled = mk(status="cancelled")
        bfac = {"_id": ObjectId(), "capacity": 12, "display_name": "Basketball Court 1"}
        b12 = make_slot(facility_id=bfac["_id"], capacity=12)
        db = FakeDb(slots=[ok, at4, over, past, cancelled, b12], facilities=[fac, bfac])
        db["slots"].find = _ne_find(db["slots"])

        dry = await migrate_slot_capacity(db, apply=False)
        self.assertEqual(len(dry["updated"]), 2)
        self.assertEqual(len(dry["over_capacity_flagged"]), 1)
        self.assertTrue(all(s["capacity"] == 6 for s in (ok, at4, over, past)))  # dry-run writes nothing

        await migrate_slot_capacity(db, apply=True)
        self.assertEqual((ok["capacity"], ok["status"]), (4, "open"))
        self.assertEqual((at4["capacity"], at4["status"]), (4, "full"))
        self.assertEqual((over["capacity"], over["status"], over["booked_count"]), (4, "full", 5))
        self.assertTrue(over["needs_capacity_review"])
        self.assertEqual(past["capacity"], 6)        # past slot untouched
        self.assertEqual(cancelled["capacity"], 6)   # cancelled slot untouched
        self.assertEqual(b12["capacity"], 12)        # 12 stays 12


if __name__ == "__main__":
    unittest.main()
