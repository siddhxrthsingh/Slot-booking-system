import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.services.booking_service import create_booking


# ---------------------------------------------------------------------------
# Minimal fake Motor-like db, matching the style used in
# test_facility_slot_retrieval.py, extended with find_one/find_one_and_update/
# insert_one/update_one so the join flow can run against it.
# ---------------------------------------------------------------------------

def matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(matches(doc, clause) for clause in expected):
                return False
            continue
        if key == "$expr":
            if not _eval_expr(doc, expected):
                return False
            continue
        actual = doc.get(key)
        if isinstance(expected, dict) and any(k.startswith("$") for k in expected):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$nin" in expected and actual in expected["$nin"]:
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$gt" in expected and not (actual is not None and actual > expected["$gt"]):
                return False
            if "$gte" in expected and not (actual is not None and actual >= expected["$gte"]):
                return False
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            continue
        if actual != expected:
            return False
    return True


def _eval_expr(doc, expr):
    op, args = next(iter(expr.items()))
    values = [_resolve(doc, a) for a in args]
    if op == "$lt":
        return values[0] < values[1]
    raise NotImplementedError(op)


def _resolve(doc, val):
    if isinstance(val, str) and val.startswith("$"):
        return doc.get(val[1:])
    return val


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, str):
            reverse = (direction if direction is not None else 1) < 0
            self.docs.sort(key=lambda d: d.get(key_or_list), reverse=reverse)
        else:
            for key, dir_ in reversed(key_or_list):
                self.docs.sort(key=lambda d: d.get(key), reverse=dir_ < 0)
        return self

    async def to_list(self, length):
        return self.docs[:length]


class FakeCollection:
    def __init__(self, docs=None, unique_keys=None):
        self.docs = list(docs or [])
        # List of tuples of field names that must be unique together, e.g.
        # [("user_id", "slot_id")] — mirrors the real `bookings` unique index.
        self.unique_keys = unique_keys or []

    def find(self, query=None):
        query = query or {}
        return FakeCursor([doc for doc in self.docs if matches(doc, query)])

    async def find_one(self, query):
        for doc in self.docs:
            if matches(doc, query):
                return doc
        return None

    async def find_one_and_update(self, query, update, return_document=True):
        # Yield control here so two concurrent callers (asyncio.gather) can
        # genuinely interleave around the read-modify-write, exercising the
        # same race window a real Motor/MongoDB round-trip would have.
        await asyncio.sleep(0)
        for doc in self.docs:
            if matches(doc, query):
                _apply_update(doc, update)
                return doc
        return None

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if matches(doc, query):
                _apply_update(doc, update)
                return
        if upsert:
            new_doc = {}
            _apply_update(new_doc, update)
            new_doc.setdefault("_id", ObjectId())
            self.docs.append(new_doc)
        return

    async def insert_one(self, doc):
        # Yield control so concurrent inserts racing on the same unique key
        # can genuinely interleave, like two real Motor round-trips would.
        await asyncio.sleep(0)
        for keys in self.unique_keys:
            key_values = tuple(doc.get(k) for k in keys)
            for existing in self.docs:
                if tuple(existing.get(k) for k in keys) == key_values:
                    raise DuplicateKeyError("duplicate key")
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return type("Result", (), {"inserted_id": doc["_id"]})()


def _apply_update(doc, update):
    for op, fields in update.items():
        if op == "$set":
            doc.update(fields)
        elif op == "$inc":
            for k, v in fields.items():
                doc[k] = doc.get(k, 0) + v
        else:
            raise NotImplementedError(op)


class FakeDb:
    def __init__(self, slots=None, bookings=None, facilities=None, bans=None):
        self.collections = {
            "slots": FakeCollection(slots),
            "bookings": FakeCollection(bookings, unique_keys=[("user_id", "slot_id")]),
            "facilities": FakeCollection(facilities),
            "bans": FakeCollection(bans),
        }

    def __getitem__(self, name):
        return self.collections[name]


def make_user(**overrides):
    base = {
        "_id": ObjectId(),
        "name": "Student One",
        "srn": "PES1UG22CS001",
        "phone": "9999999999",
        "branch": "CSE",
        "program": "B.Tech",
        "semester": "6",
        "section": "A",
        "campus": "RR",
    }
    base.update(overrides)
    return base


def future_date(days=3):
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def make_slot(**overrides):
    base = {
        "_id": ObjectId(),
        "facility_id": ObjectId(),
        "facility_name": "Badminton Court 1",
        "sport": "Badminton",
        "date": future_date(),
        "start_time": "09:00",
        "end_time": "10:00",
        "venue": "Badminton Court 1",
        "campus": "RR",
        "capacity": 6,
        "booked_count": 0,
        "status": "open",
        "duration_minutes": 60,
        "slot_type": "generated",
        "is_manual": False,
        "leader_user_id": None,
    }
    base.update(overrides)
    return base


def make_facility(slot, capacity):
    return {"_id": slot["facility_id"], "capacity": capacity}


class JoinBookingTests(unittest.IsolatedAsyncioTestCase):
    async def test_join_success_creates_confirmed_booking_with_snapshot(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        self.assertEqual(booking["status"], "confirmed")
        self.assertIsNotNone(booking["joined_at"])
        self.assertEqual(booking["user_snapshot"]["srn"], "PES1UG22CS001")
        self.assertEqual(booking["user_snapshot"]["phone"], "9999999999")
        self.assertEqual(db["slots"].docs[0]["booked_count"], 1)

    async def test_first_participant_becomes_leader(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        self.assertTrue(booking["is_leader"])
        self.assertEqual(str(db["slots"].docs[0]["leader_user_id"]), str(user["_id"]))

    async def test_leader_is_whoever_actually_takes_booked_count_to_one_under_concurrency(self):
        # Two joins fired concurrently (interleaved via asyncio.gather) race
        # for the same slot. Exactly one of them must atomically take
        # booked_count 0 -> 1, and that request — not whichever happened to
        # run a later "claim leadership" step — must be the leader.
        slot = make_slot()
        user_a = make_user()
        user_b = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        results = await asyncio.gather(
            create_booking(db, user=user_a, slot_id=str(slot["_id"])),
            create_booking(db, user=user_b, slot_id=str(slot["_id"])),
        )

        leaders = [b for b in results if b["is_leader"]]
        self.assertEqual(len(leaders), 1)
        self.assertEqual(db["slots"].docs[0]["booked_count"], 2)

        leader_booking = leaders[0]
        self.assertEqual(
            str(db["slots"].docs[0]["leader_user_id"]), str(leader_booking["user_id"])
        )

    async def test_second_participant_joins_but_is_not_leader(self):
        slot = make_slot()
        leader = make_user()
        second = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        await create_booking(db, user=leader, slot_id=str(slot["_id"]))
        booking2 = await create_booking(db, user=second, slot_id=str(slot["_id"]))

        self.assertFalse(booking2["is_leader"])
        self.assertEqual(db["slots"].docs[0]["booked_count"], 2)
        self.assertEqual(str(db["slots"].docs[0]["leader_user_id"]), str(leader["_id"]))

    async def test_full_slot_rejects_further_joins(self):
        slot = make_slot(capacity=6, booked_count=6, status="full")
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        with self.assertRaises(LookupError):
            await create_booking(db, user=user, slot_id=str(slot["_id"]))

    async def test_capacity_protection_when_last_seat_taken_concurrently(self):
        # Facility capacity is 6; slot already at 5 booked. Two joins race for
        # the last seat — only one should succeed, simulating concurrent
        # atomic increments against the same document.
        slot = make_slot(capacity=6, booked_count=5, status="open")
        facility = make_facility(slot, 6)
        user_a = make_user()
        user_b = make_user()
        db = FakeDb(slots=[slot], facilities=[facility])

        await create_booking(db, user=user_a, slot_id=str(slot["_id"]))
        self.assertEqual(db["slots"].docs[0]["status"], "full")

        with self.assertRaises((ValueError, LookupError)):
            await create_booking(db, user=user_b, slot_id=str(slot["_id"]))

        self.assertEqual(db["slots"].docs[0]["booked_count"], 6)

    async def test_duplicate_active_join_rejected(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        await create_booking(db, user=user, slot_id=str(slot["_id"]))
        with self.assertRaises(ValueError):
            await create_booking(db, user=user, slot_id=str(slot["_id"]))

    async def test_rejoin_after_leaving_same_slot_rejected(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(
            slots=[slot],
            facilities=[make_facility(slot, 6)],
            bookings=[{
                "_id": ObjectId(),
                "user_id": user["_id"],
                "slot_id": slot["_id"],
                "status": "cancelled",
            }],
        )

        with self.assertRaises(ValueError) as ctx:
            await create_booking(db, user=user, slot_id=str(slot["_id"]))
        self.assertIn("cannot rejoin", str(ctx.exception))

    async def test_daily_two_active_slot_limit_enforced(self):
        date = future_date()
        slot1 = make_slot(date=date, start_time="09:00", end_time="10:00", sport="Badminton")
        slot2 = make_slot(date=date, start_time="11:00", end_time="12:00", sport="Table Tennis")
        slot3 = make_slot(date=date, start_time="14:00", end_time="15:00", sport="Squash")
        user = make_user()
        db = FakeDb(
            slots=[slot1, slot2, slot3],
            facilities=[make_facility(slot1, 6), make_facility(slot2, 6), make_facility(slot3, 6)],
        )

        await create_booking(db, user=user, slot_id=str(slot1["_id"]))
        await create_booking(db, user=user, slot_id=str(slot2["_id"]))

        with self.assertRaises(ValueError) as ctx:
            await create_booking(db, user=user, slot_id=str(slot3["_id"]))
        self.assertIn("active bookings on this day", str(ctx.exception))

    async def test_concurrent_duplicate_join_by_same_user_does_not_double_book(self):
        # Same user fires two join requests for the same slot at once (e.g. a
        # double-click). The pre-check for an existing booking isn't atomic
        # with the insert, so both requests can pass it before either
        # inserts. The unique (user_id, slot_id) index must be the backstop:
        # exactly one booking should survive and the reserved seat from the
        # loser must be released, not leaked.
        slot = make_slot(capacity=6, booked_count=0, status="open")
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        results = await asyncio.gather(
            create_booking(db, user=user, slot_id=str(slot["_id"])),
            create_booking(db, user=user, slot_id=str(slot["_id"])),
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], ValueError)

        active_bookings = [b for b in db["bookings"].docs if b["status"] != "cancelled"]
        self.assertEqual(len(active_bookings), 1)
        self.assertEqual(db["slots"].docs[0]["booked_count"], 1)
        self.assertTrue(active_bookings[0]["is_leader"])
        self.assertEqual(str(db["slots"].docs[0]["leader_user_id"]), str(user["_id"]))

    async def test_overlapping_active_bookings_rejected(self):
        date = future_date()
        slot1 = make_slot(date=date, start_time="09:00", end_time="10:30", duration_minutes=90, sport="Badminton")
        slot2 = make_slot(date=date, start_time="10:00", end_time="11:00", duration_minutes=60, sport="Squash")
        user = make_user()
        db = FakeDb(
            slots=[slot1, slot2],
            facilities=[make_facility(slot1, 6), make_facility(slot2, 6)],
        )

        await create_booking(db, user=user, slot_id=str(slot1["_id"]))
        with self.assertRaises(ValueError) as ctx:
            await create_booking(db, user=user, slot_id=str(slot2["_id"]))
        self.assertIn("Time clash", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
