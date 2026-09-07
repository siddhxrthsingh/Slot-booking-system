import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.services.booking_service import cancel_booking, check_user_ban, create_booking
from tests.test_booking_join_service import (
    FakeCollection,
    FakeDb,
    make_facility,
    make_slot,
    make_user,
)

IST = ZoneInfo("Asia/Kolkata")


class LeaveBookingTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_leave_marks_booking_cancelled_with_actor_and_timestamp(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        updated = await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        self.assertEqual(updated["status"], "cancelled")
        self.assertIsNotNone(updated["cancelled_at"])
        self.assertEqual(str(updated["cancelled_by"]), str(user["_id"]))

    async def test_booking_record_is_preserved_not_deleted(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        stored = await db["bookings"].find_one({"_id": booking["_id"]})
        self.assertIsNotNone(stored)
        self.assertEqual(stored["status"], "cancelled")

    async def test_booked_count_decrements_exactly_once(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))
        self.assertEqual(db["slots"].docs[0]["booked_count"], 1)

        await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        self.assertEqual(db["slots"].docs[0]["booked_count"], 0)

    async def test_duplicate_cancellation_does_not_decrement_twice(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        await cancel_booking(db, str(booking["_id"]), str(user["_id"]))
        with self.assertRaises(ValueError):
            await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        self.assertEqual(db["slots"].docs[0]["booked_count"], 0)

    async def test_booked_count_never_goes_negative(self):
        slot = make_slot(booked_count=0)
        user = make_user()
        db = FakeDb(
            slots=[slot],
            facilities=[make_facility(slot, 6)],
            bookings=[{
                "_id": ObjectId(),
                "user_id": user["_id"],
                "slot_id": slot["_id"],
                "sport": slot["sport"],
                "status": "confirmed",
                "is_leader": False,
                "joined_at": datetime.now(timezone.utc),
            }],
        )

        await cancel_booking(db, str(db["bookings"].docs[0]["_id"]), str(user["_id"]))

        self.assertEqual(db["slots"].docs[0]["booked_count"], 0)

    async def test_non_leader_leaves_leader_unchanged(self):
        slot = make_slot()
        leader = make_user()
        second = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        await create_booking(db, user=leader, slot_id=str(slot["_id"]))
        booking2 = await create_booking(db, user=second, slot_id=str(slot["_id"]))

        await cancel_booking(db, str(booking2["_id"]), str(second["_id"]))

        self.assertEqual(str(db["slots"].docs[0]["leader_user_id"]), str(leader["_id"]))
        self.assertEqual(db["slots"].docs[0]["booked_count"], 1)

    async def test_promotion_skips_candidate_cancelled_concurrently(self):
        # Simulates the TOCTOU race: the earliest-joined candidate is
        # selected for promotion, but before the guarded promotion write
        # executes, that same candidate's own leave request commits first.
        # The promotion write must then fail its status guard, and the next
        # earliest ACTIVE participant must be promoted instead — a cancelled
        # booking must never end up as leader.
        slot = make_slot()
        leader = make_user()
        candidate = make_user()
        fallback = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        leader_booking = await create_booking(db, user=leader, slot_id=str(slot["_id"]))
        candidate_booking = await create_booking(db, user=candidate, slot_id=str(slot["_id"]))
        fallback_booking = await create_booking(db, user=fallback, slot_id=str(slot["_id"]))

        class RacyBookingCollection(FakeCollection):
            """Cancels `candidate_booking` the instant its promotion write is
            attempted, simulating it losing the race to its own leave call."""

            def __init__(self, docs, candidate_id):
                super().__init__(docs)
                self.candidate_id = candidate_id
                self.raced = False

            async def find_one_and_update(self, query, update, return_document=True):
                if (
                    not self.raced
                    and query.get("_id") == self.candidate_id
                    and update.get("$set", {}).get("is_leader") is True
                ):
                    self.raced = True
                    for doc in self.docs:
                        if doc["_id"] == self.candidate_id:
                            doc["status"] = "cancelled"
                            doc["cancelled_at"] = datetime.now(timezone.utc)
                return await super().find_one_and_update(query, update, return_document)

        db.collections["bookings"] = RacyBookingCollection(
            db["bookings"].docs, candidate_booking["_id"]
        )

        await cancel_booking(db, str(leader_booking["_id"]), str(leader["_id"]))

        stored_candidate = await db["bookings"].find_one({"_id": candidate_booking["_id"]})
        stored_fallback = await db["bookings"].find_one({"_id": fallback_booking["_id"]})

        self.assertEqual(stored_candidate["status"], "cancelled")
        self.assertFalse(stored_candidate["is_leader"])
        self.assertTrue(stored_fallback["is_leader"])
        self.assertEqual(str(db["slots"].docs[0]["leader_user_id"]), str(fallback["_id"]))

    async def test_leader_leaves_earliest_remaining_participant_promoted(self):
        slot = make_slot()
        leader = make_user()
        second = make_user()
        third = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        leader_booking = await create_booking(db, user=leader, slot_id=str(slot["_id"]))
        second_booking = await create_booking(db, user=second, slot_id=str(slot["_id"]))
        await create_booking(db, user=third, slot_id=str(slot["_id"]))

        await cancel_booking(db, str(leader_booking["_id"]), str(leader["_id"]))

        self.assertEqual(str(db["slots"].docs[0]["leader_user_id"]), str(second["_id"]))
        promoted = await db["bookings"].find_one({"_id": second_booking["_id"]})
        self.assertTrue(promoted["is_leader"])

    async def test_last_participant_leaves_no_leader_remains(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        self.assertIsNone(db["slots"].docs[0]["leader_user_id"])

    async def test_late_cancellation_applies_ban(self):
        date = datetime.now(IST) + timedelta(minutes=30)
        slot = make_slot(date=date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc),
                          start_time=date.strftime("%H:%M"),
                          end_time=(date + timedelta(hours=1)).strftime("%H:%M"))
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        updated = await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        self.assertTrue(updated["late_cancel"])
        ban = await check_user_ban(db, user["_id"])
        self.assertIsNotNone(ban)

    async def test_early_cancellation_frees_daily_quota(self):
        date = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        slot1 = make_slot(date=date, start_time="09:00", end_time="10:00", sport="Badminton")
        slot2 = make_slot(date=date, start_time="11:00", end_time="12:00", sport="Table Tennis")
        slot3 = make_slot(date=date, start_time="14:00", end_time="15:00", sport="Squash")
        user = make_user()
        db = FakeDb(
            slots=[slot1, slot2, slot3],
            facilities=[make_facility(slot1, 6), make_facility(slot2, 6), make_facility(slot3, 6)],
        )

        b1 = await create_booking(db, user=user, slot_id=str(slot1["_id"]))
        await create_booking(db, user=user, slot_id=str(slot2["_id"]))

        # Cancel the first booking (well before the window) to free up quota.
        await cancel_booking(db, str(b1["_id"]), str(user["_id"]))

        # Should now be allowed to join a third slot on the same day.
        booking3 = await create_booking(db, user=user, slot_id=str(slot3["_id"]))
        self.assertEqual(booking3["status"], "confirmed")

    async def test_banned_user_cannot_join_another_slot(self):
        date = datetime.now(IST) + timedelta(minutes=30)
        late_slot = make_slot(date=date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc),
                               start_time=date.strftime("%H:%M"),
                               end_time=(date + timedelta(hours=1)).strftime("%H:%M"))
        other_slot = make_slot(date=(datetime.now(timezone.utc) + timedelta(days=5)))
        user = make_user()
        db = FakeDb(
            slots=[late_slot, other_slot],
            facilities=[make_facility(late_slot, 6), make_facility(other_slot, 6)],
        )
        booking = await create_booking(db, user=user, slot_id=str(late_slot["_id"]))
        await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        with self.assertRaises(ValueError) as ctx:
            await create_booking(db, user=user, slot_id=str(other_slot["_id"]))
        self.assertIn("suspended", str(ctx.exception))

    async def test_cancelled_participant_cannot_rejoin_same_slot(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        with self.assertRaises(ValueError) as ctx:
            await create_booking(db, user=user, slot_id=str(slot["_id"]))
        self.assertIn("cannot rejoin", str(ctx.exception))

    async def test_leaving_already_started_slot_is_treated_as_late_cancel(self):
        started = datetime.now(IST) - timedelta(minutes=15)
        slot = make_slot(
            date=started.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc),
            start_time=started.strftime("%H:%M"),
            end_time=(started + timedelta(hours=1)).strftime("%H:%M"),
        )
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))

        updated = await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        self.assertTrue(updated["late_cancel"])
        ban = await check_user_ban(db, user["_id"])
        self.assertIsNotNone(ban)


if __name__ == "__main__":
    unittest.main()
