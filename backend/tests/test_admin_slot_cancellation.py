import unittest
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.services.admin_service import cancel_slot
from app.services.booking_service import cancel_booking, check_user_ban, create_booking
from tests.test_booking_join_service import FakeDb, make_facility, make_slot, make_user


class AdminSlotCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_slot_marked_cancelled_not_deleted(self):
        slot = make_slot()
        student = make_user()
        admin_id = str(ObjectId())
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        await create_booking(db, user=student, slot_id=str(slot["_id"]))

        await cancel_slot(db, str(slot["_id"]), admin_id)

        stored_slot = await db["slots"].find_one({"_id": slot["_id"]})
        self.assertIsNotNone(stored_slot)
        self.assertEqual(stored_slot["status"], "cancelled")

    async def test_active_participants_cancelled_with_admin_as_actor(self):
        slot = make_slot()
        student = make_user()
        admin_id = str(ObjectId())
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))

        cancelled_count = await cancel_slot(db, str(slot["_id"]), admin_id)

        stored_booking = await db["bookings"].find_one({"_id": booking["_id"]})
        self.assertEqual(cancelled_count, 1)
        self.assertEqual(stored_booking["status"], "cancelled")
        self.assertEqual(str(stored_booking["cancelled_by"]), admin_id)
        self.assertIsNotNone(stored_booking["cancelled_at"])

    async def test_booking_history_preserved_not_deleted(self):
        slot = make_slot()
        student = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))

        await cancel_slot(db, str(slot["_id"]), str(ObjectId()))

        self.assertEqual(len(db["bookings"].docs), 1)
        stored_booking = await db["bookings"].find_one({"_id": booking["_id"]})
        self.assertIsNotNone(stored_booking)

    async def test_no_stale_leader_after_full_slot_cancellation(self):
        slot = make_slot()
        leader = make_user()
        second = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        await create_booking(db, user=leader, slot_id=str(slot["_id"]))
        await create_booking(db, user=second, slot_id=str(slot["_id"]))
        self.assertIsNotNone(db["slots"].docs[0]["leader_user_id"])  # sanity check

        await cancel_slot(db, str(slot["_id"]), str(ObjectId()))

        self.assertIsNone(db["slots"].docs[0]["leader_user_id"])

    async def test_missing_slot_raises_lookup_error(self):
        db = FakeDb(slots=[], facilities=[])

        with self.assertRaises(LookupError):
            await cancel_slot(db, str(ObjectId()), str(ObjectId()))

    async def test_already_cancelled_booking_is_left_untouched_and_not_recounted(self):
        slot = make_slot()
        active_student = make_user()
        already_left_student = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        active_booking = await create_booking(db, user=active_student, slot_id=str(slot["_id"]))
        left_booking = await create_booking(db, user=already_left_student, slot_id=str(slot["_id"]))
        await cancel_booking(db, str(left_booking["_id"]), str(already_left_student["_id"]))
        left_cancelled_at_before = (
            await db["bookings"].find_one({"_id": left_booking["_id"]})
        )["cancelled_at"]

        cancelled_count = await cancel_slot(db, str(slot["_id"]), str(ObjectId()))

        self.assertEqual(cancelled_count, 1)
        stored_left = await db["bookings"].find_one({"_id": left_booking["_id"]})
        self.assertEqual(stored_left["cancelled_at"], left_cancelled_at_before)
        stored_active = await db["bookings"].find_one({"_id": active_booking["_id"]})
        self.assertEqual(stored_active["status"], "cancelled")

    async def test_admin_slot_cancellation_does_not_ban_participants(self):
        near = datetime.now(timezone.utc) + timedelta(minutes=30)
        slot = make_slot(
            date=near.replace(hour=0, minute=0, second=0, microsecond=0),
            start_time=near.strftime("%H:%M"),
            end_time=(near + timedelta(hours=1)).strftime("%H:%M"),
        )
        student = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        await create_booking(db, user=student, slot_id=str(slot["_id"]))

        await cancel_slot(db, str(slot["_id"]), str(ObjectId()))

        ban = await check_user_ban(db, student["_id"])
        self.assertIsNone(ban)


if __name__ == "__main__":
    unittest.main()
