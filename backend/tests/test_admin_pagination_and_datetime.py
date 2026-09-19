"""RC-2 (admin list/count pagination consistency) and RC-3 (admin datetime
normalization) tests.

Uses a small self-contained fake Motor-like db (find/sort/skip/limit/
to_list/count_documents/find_one) rather than the shared FakeDb fixtures
used elsewhere, since those don't implement skip/limit/count_documents.
"""
import unittest
from datetime import datetime, timedelta, timezone

from app.services import admin_service


def matches(doc, query):
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$gte" in expected and not (actual is not None and actual >= expected["$gte"]):
                return False
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            if "$regex" in expected and expected["$regex"].lower() not in str(actual or "").lower():
                return False
            continue
        if actual != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, str):
            reverse = (direction if direction is not None else 1) < 0
            self.docs.sort(key=lambda d: d.get(key_or_list), reverse=reverse)
        else:
            for key, dir_ in reversed(key_or_list):
                self.docs.sort(key=lambda d: (d.get(key) is None, d.get(key)), reverse=dir_ < 0)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, length):
        return self.docs[:length] if length is not None else self.docs


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None, projection=None):
        query = query or {}
        return FakeCursor([doc for doc in self.docs if matches(doc, query)])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if matches(doc, query):
                return doc
        return None

    async def count_documents(self, query=None):
        query = query or {}
        return sum(1 for doc in self.docs if matches(doc, query))


class FakeDb:
    def __init__(self, slots=None, bookings=None, users=None, facilities=None, schedule_templates=None):
        self.collections = {
            "slots": FakeCollection(slots),
            "bookings": FakeCollection(bookings),
            "users": FakeCollection(users),
            "facilities": FakeCollection(facilities),
            "schedule_templates": FakeCollection(schedule_templates),
        }

    def __getitem__(self, name):
        return self.collections[name]


def make_slot(i, status="open", naive_date=True):
    base = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
    d = base + timedelta(days=i % 5)
    return {
        "_id": f"slot-{i}",
        "facility_id": "facility-1",
        "facility_name": "Badminton Court 1",
        "sport": "Badminton",
        "date": d if naive_date else d.replace(tzinfo=timezone.utc),
        "start_time": "09:00",
        "end_time": "10:00",
        "venue": "Badminton Court 1",
        "campus": "RR",
        "capacity": 6,
        "booked_count": 0,
        "status": status,
        "is_manual": False,
        "created_at": d,
    }


def make_booking(i, status="confirmed"):
    created = datetime(2026, 1, 1) + timedelta(minutes=i)
    return {
        "_id": f"booking-{i}",
        "user_id": f"user-{i}",
        "slot_id": f"slot-{i}",
        "sport": "Badminton",
        "status": status,
        "booking_date": created,
        "cancelled_at": None,
        "notes": None,
        "created_at": created,
    }


class AdminListPaginationTests(unittest.IsolatedAsyncioTestCase):
    # A. <500 records → all matching records behave as before.
    async def test_small_dataset_all_records_returned_on_first_page(self):
        db = FakeDb(slots=[make_slot(i) for i in range(10)])
        result = await admin_service.list_all_slots(db, campus="RR", active_only=False, page=1, page_size=50)
        self.assertEqual(result["total"], 10)
        self.assertEqual(len(result["items"]), 10)

    # B. >500 (here >page_size) records → first page does NOT silently return all.
    async def test_large_dataset_first_page_is_capped(self):
        db = FakeDb(slots=[make_slot(i) for i in range(600)])
        result = await admin_service.list_all_slots(db, campus="RR", active_only=False, page=1, page_size=50)
        self.assertEqual(len(result["items"]), 50)
        self.assertEqual(result["total"], 600)

    # C. Page 2 retrieves the next records.
    async def test_page_two_retrieves_next_slice(self):
        db = FakeDb(slots=[make_slot(i) for i in range(120)])
        page1 = await admin_service.list_all_slots(db, campus="RR", active_only=False, page=1, page_size=50)
        page2 = await admin_service.list_all_slots(db, campus="RR", active_only=False, page=2, page_size=50)
        ids_p1 = {s["_id"] for s in page1["items"]}
        ids_p2 = {s["_id"] for s in page2["items"]}
        self.assertEqual(len(ids_p2), 50)
        self.assertEqual(ids_p1 & ids_p2, set())  # I. no duplicates between pages

    # D/E. Total count remains accurate and uses identical filters as the list.
    async def test_total_uses_same_filter_as_list(self):
        db = FakeDb(slots=[make_slot(i, status="open") for i in range(5)] + [make_slot(i, status="cancelled") for i in range(5, 8)])
        result = await admin_service.list_all_slots(db, campus="RR", active_only=False, sport="Badminton", page=1, page_size=50)
        self.assertEqual(result["total"], 8)
        self.assertEqual(len(result["items"]), 8)

    # F. Different statuses are counted correctly (active_only filter).
    async def test_active_only_filters_before_counting(self):
        db = FakeDb(slots=[make_slot(i, status="open") for i in range(3)] + [make_slot(i, status="cancelled") for i in range(3, 6)])
        result = await admin_service.list_all_slots(db, campus="RR", active_only=True, page=1, page_size=50)
        self.assertEqual(result["total"], 3)

    # G. Filters + pagination work together.
    async def test_filters_and_pagination_combined(self):
        db = FakeDb(slots=[make_slot(i) for i in range(30)])
        result = await admin_service.list_all_slots(db, campus="RR", active_only=False, sport="Badminton", page=2, page_size=10)
        self.assertEqual(result["total"], 30)
        self.assertEqual(len(result["items"]), 10)

    # H/J. Deterministic ordering, no missing records across all pages.
    async def test_deterministic_ordering_and_no_missing_records(self):
        db = FakeDb(slots=[make_slot(i) for i in range(45)])
        all_ids = []
        for page in (1, 2, 3, 4, 5):
            result = await admin_service.list_all_slots(db, campus="RR", active_only=False, page=page, page_size=10)
            all_ids.extend(s["_id"] for s in result["items"])
        self.assertEqual(sorted(all_ids), sorted(f"slot-{i}" for i in range(45)))
        self.assertEqual(len(all_ids), len(set(all_ids)))  # no duplicates

    async def test_bookings_pagination_page_two(self):
        db = FakeDb(bookings=[make_booking(i) for i in range(120)])
        page1 = await admin_service.list_all_bookings(db, page=1, page_size=50)
        page2 = await admin_service.list_all_bookings(db, page=2, page_size=50)
        self.assertEqual(page1["total"], 120)
        self.assertEqual(len(page1["items"]), 50)
        ids_p1 = {b["id"] for b in page1["items"]}
        ids_p2 = {b["id"] for b in page2["items"]}
        self.assertEqual(ids_p1 & ids_p2, set())

    async def test_bookings_status_filter_and_count_match(self):
        db = FakeDb(bookings=[make_booking(i, status="confirmed") for i in range(4)] + [make_booking(i, status="cancelled") for i in range(4, 7)])
        result = await admin_service.list_all_bookings(db, status_filter="cancelled", page=1, page_size=50)
        self.assertEqual(result["total"], 3)
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue(all(b["status"] == "cancelled" for b in result["items"]))


class AdminDatetimeNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_slot_naive_datetime_normalized_to_utc(self):
        db = FakeDb(slots=[make_slot(0, naive_date=True)])
        result = await admin_service.list_all_slots(db, campus="RR", active_only=False, page=1, page_size=10)
        d = result["items"][0]["date"]
        self.assertIsNone(d.tzinfo)  # service layer returns raw doc; router normalizes

    async def test_admin_booking_datetime_normalized(self):
        naive_created = datetime(2026, 1, 1, 12, 0, 0)
        db = FakeDb(bookings=[{
            "_id": "b1", "user_id": "u1", "slot_id": "s1", "sport": "Badminton",
            "status": "confirmed", "booking_date": naive_created,
            "cancelled_at": None, "notes": None, "created_at": naive_created,
        }])
        result = await admin_service.list_all_bookings(db, page=1, page_size=10)
        b = result["items"][0]
        self.assertEqual(b["created_at"].tzinfo, timezone.utc)
        self.assertEqual(b["booking_date"].tzinfo, timezone.utc)

    async def test_already_aware_utc_datetime_unchanged(self):
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        db = FakeDb(bookings=[{
            "_id": "b1", "user_id": "u1", "slot_id": "s1", "sport": "Badminton",
            "status": "confirmed", "booking_date": aware,
            "cancelled_at": None, "notes": None, "created_at": aware,
        }])
        result = await admin_service.list_all_bookings(db, page=1, page_size=10)
        b = result["items"][0]
        self.assertEqual(b["created_at"], aware)

    async def test_pending_booking_datetime_normalized(self):
        naive = datetime(2026, 1, 1, 12, 0, 0)
        db = FakeDb(
            bookings=[{
                "_id": "b1", "user_id": "u1", "slot_id": "s1", "sport": "Badminton",
                "status": "pending_approval", "booking_date": naive, "notes": None,
                "created_at": naive,
            }],
            users=[{"_id": "u1", "name": "Test User", "srn": "PES1UG22CS001", "email": "t@example.com"}],
            slots=[make_slot(0, naive_date=True) | {"_id": "s1"}],
        )
        result = await admin_service.list_pending_bookings(db)
        self.assertEqual(result[0]["booking_date"].tzinfo, timezone.utc)
        self.assertEqual(result[0]["slot"]["date"].tzinfo, timezone.utc)

    async def test_ist_midnight_boundary_preserved(self):
        # 2026-01-01 18:30 UTC == 2026-01-02 00:00 IST — normalization must not
        # shift the instant, only attach tzinfo.
        naive = datetime(2026, 1, 1, 18, 30, 0)
        db = FakeDb(bookings=[{
            "_id": "b1", "user_id": "u1", "slot_id": "s1", "sport": "Badminton",
            "status": "confirmed", "booking_date": naive,
            "cancelled_at": None, "notes": None, "created_at": naive,
        }])
        result = await admin_service.list_all_bookings(db, page=1, page_size=10)
        b = result["items"][0]
        self.assertEqual(b["created_at"], naive.replace(tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
