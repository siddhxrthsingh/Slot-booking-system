"""
Free Speed Plan Step 2: collapse N+1 query loops in booking/admin list
endpoints. Each test here proves BOTH that the response content is
unchanged AND that per-item user/slot lookups no longer scale with the
number of items (a fixed, small number of queries instead of 2N).
"""
import unittest
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.routers.admin import list_bans
from app.services import admin_service
from app.services.booking_service import get_user_bookings
from tests.test_admin_pagination_and_datetime import FakeDb as PagedFakeDb
from tests.test_booking_join_service import FakeDb as JoinFakeDb
from tests.test_booking_join_service import make_user


def _counting(collection) -> dict:
    """Wrap find()/find_one() on a fake collection to count calls."""
    counts = {"find": 0, "find_one": 0}
    original_find = collection.find
    original_find_one = collection.find_one

    def counting_find(*args, **kwargs):
        counts["find"] += 1
        return original_find(*args, **kwargs)

    async def counting_find_one(*args, **kwargs):
        counts["find_one"] += 1
        return await original_find_one(*args, **kwargs)

    collection.find = counting_find
    collection.find_one = counting_find_one
    return counts


def _booking(user_id, slot_id, status="confirmed", order=0, **overrides):
    created = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=order)
    base = {
        "_id": f"booking-{user_id}-{slot_id}",
        "user_id": user_id,
        "slot_id": slot_id,
        "sport": "Badminton",
        "status": status,
        "booking_date": created,
        "cancelled_at": None,
        "notes": None,
        "created_at": created,
    }
    base.update(overrides)
    return base


class AdminBookingListNPlusOneTests(unittest.IsolatedAsyncioTestCase):
    """list_all_bookings / list_pending_bookings need count_documents/skip/
    limit, so these use the richer FakeDb from the pagination test module."""

    def _db_with_n_bookings(self, n):
        users = [make_user(_id=f"user-{i}") for i in range(n)]
        bookings = [_booking(f"user-{i}", f"slot-{i}", order=i) for i in range(n)]
        return PagedFakeDb(bookings=bookings, users=users)

    async def test_list_all_bookings_query_count_independent_of_page_size(self):
        db = self._db_with_n_bookings(20)
        users_counts = _counting(db["users"])
        slots_counts = _counting(db["slots"])

        result = await admin_service.list_all_bookings(db, page=1, page_size=50)

        self.assertEqual(len(result["items"]), 20)
        # One batch $in query for users, one for slots — not one per booking.
        self.assertEqual(users_counts["find"], 1)
        self.assertEqual(slots_counts["find"], 1)
        self.assertEqual(users_counts["find_one"], 0)
        self.assertEqual(slots_counts["find_one"], 0)

    async def test_list_all_bookings_content_unchanged(self):
        db = self._db_with_n_bookings(3)
        result = await admin_service.list_all_bookings(db, page=1, page_size=50)

        self.assertEqual({i["user"]["id"] for i in result["items"]}, {"user-0", "user-1", "user-2"})
        self.assertTrue(all("srn" in i["user"] for i in result["items"]))

    async def test_list_pending_bookings_query_count_independent_of_count(self):
        n = 15
        users = [make_user(_id=f"user-{i}") for i in range(n)]
        bookings = [
            _booking(f"user-{i}", f"slot-{i}", status="pending_approval", order=i)
            for i in range(n)
        ]
        db = PagedFakeDb(bookings=bookings, users=users)
        users_counts = _counting(db["users"])
        slots_counts = _counting(db["slots"])

        result = await admin_service.list_pending_bookings(db)

        self.assertEqual(len(result), n)
        self.assertEqual(users_counts["find"], 1)
        self.assertEqual(slots_counts["find"], 1)

    async def test_missing_user_or_slot_does_not_break_enrichment(self):
        # A booking whose user/slot no longer exist must still enrich as
        # None for that field, exactly as the old per-item find_one did.
        bookings = [_booking("ghost-user", "ghost-slot")]
        db = PagedFakeDb(bookings=bookings, users=[])

        result = await admin_service.list_all_bookings(db, page=1, page_size=50)

        self.assertIsNone(result["items"][0]["user"])
        self.assertIsNone(result["items"][0]["slot"])


class ListBansNPlusOneTests(unittest.IsolatedAsyncioTestCase):
    """list_bans filters bans with {"$gt": now}, which the join-service
    fixture's matcher supports (and which doesn't need count_documents)."""

    async def test_list_bans_query_count_independent_of_ban_count(self):
        n = 10
        future = datetime.now(timezone.utc) + timedelta(days=1)
        users = [make_user(_id=f"user-{i}") for i in range(n)]
        bans = [
            {"_id": f"ban-{i}", "user_id": f"user-{i}", "banned_until": future, "reason": "x"}
            for i in range(n)
        ]
        db = JoinFakeDb(users=users, bans=bans)
        users_counts = _counting(db["users"])

        resp = await list_bans(db=db, admin={"_id": "admin-1"})

        self.assertEqual(len(resp["data"]), n)
        self.assertEqual(users_counts["find"], 1)
        self.assertEqual(users_counts["find_one"], 0)
        self.assertTrue(all(b["user_srn"] is not None for b in resp["data"]))

    async def test_expired_ban_is_excluded(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        db = JoinFakeDb(
            users=[make_user(_id="user-0")],
            bans=[{"_id": "ban-0", "user_id": "user-0", "banned_until": past, "reason": "x"}],
        )

        resp = await list_bans(db=db, admin={"_id": "admin-1"})

        self.assertEqual(resp["data"], [])


class GetUserBookingsNPlusOneTests(unittest.IsolatedAsyncioTestCase):
    async def test_my_bookings_query_count_independent_of_booking_count(self):
        user_id = ObjectId()
        n = 12
        slots = []
        bookings = []
        for i in range(n):
            slot_id = ObjectId()
            slots.append({
                "_id": slot_id,
                "date": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
                "start_time": "09:00", "end_time": "10:00",
                "venue": "Court", "campus": "RR",
            })
            bookings.append({
                "_id": ObjectId(), "user_id": user_id, "slot_id": slot_id,
                "sport": "Badminton", "status": "confirmed",
                "booking_date": datetime.now(timezone.utc),
                "cancelled_at": None, "notes": None,
                "created_at": datetime.now(timezone.utc),
            })
        db = JoinFakeDb(bookings=bookings, slots=slots)
        slots_counts = _counting(db["slots"])

        result = await get_user_bookings(db, str(user_id))

        self.assertEqual(len(result), n)
        self.assertEqual(slots_counts["find"], 1)
        self.assertEqual(slots_counts["find_one"], 0)


if __name__ == "__main__":
    unittest.main()
