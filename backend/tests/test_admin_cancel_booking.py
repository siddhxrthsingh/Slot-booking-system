import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.services.booking_service import cancel_booking, check_user_ban, create_booking
from tests.test_booking_join_service import FakeDb, make_facility, make_slot, make_user

IST = ZoneInfo("Asia/Kolkata")


class AdminCancelBookingTests(unittest.IsolatedAsyncioTestCase):
    """Admin force-cancellation (routers/admin.py's admin_cancel_booking) now
    delegates to booking_service.cancel_booking with a separate actor_id.
    These tests exercise that same service-level call the router makes,
    consistent with this repo's existing service-level test conventions."""

    async def test_admin_cancellation_marks_cancelled_and_records_admin_as_actor(self):
        slot = make_slot()
        student = make_user()
        admin_id = ObjectId()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))

        updated = await cancel_booking(
            db, str(booking["_id"]), str(student["_id"]), actor_id=str(admin_id)
        )

        self.assertEqual(updated["status"], "cancelled")
        self.assertEqual(str(updated["cancelled_by"]), str(admin_id))
        # The booking's own user_id (owner) must remain the student, not the admin.
        self.assertEqual(str(updated["user_id"]), str(student["_id"]))

    async def test_booked_count_decrements_safely_on_admin_cancel(self):
        slot = make_slot()
        student = make_user()
        admin_id = ObjectId()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))
        self.assertEqual(db["slots"].docs[0]["booked_count"], 1)

        await cancel_booking(db, str(booking["_id"]), str(student["_id"]), actor_id=str(admin_id))

        self.assertEqual(db["slots"].docs[0]["booked_count"], 0)

    async def test_full_slot_reopens_on_admin_cancel(self):
        slot = make_slot(capacity=1, booked_count=1, status="full")
        student = make_user()
        admin_id = ObjectId()
        db = FakeDb(
            slots=[slot],
            facilities=[make_facility(slot, 1)],
            bookings=[{
                "_id": ObjectId(),
                "user_id": student["_id"],
                "slot_id": slot["_id"],
                "sport": slot["sport"],
                "status": "confirmed",
                "is_leader": True,
                "joined_at": datetime.now(timezone.utc),
            }],
        )
        booking_id = db["bookings"].docs[0]["_id"]

        await cancel_booking(db, str(booking_id), str(student["_id"]), actor_id=str(admin_id))

        self.assertEqual(db["slots"].docs[0]["status"], "open")
        self.assertEqual(db["slots"].docs[0]["booked_count"], 0)

    async def test_admin_cancelling_leader_promotes_next_active_participant(self):
        slot = make_slot()
        leader = make_user()
        second = make_user()
        admin_id = ObjectId()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        leader_booking = await create_booking(db, user=leader, slot_id=str(slot["_id"]))
        second_booking = await create_booking(db, user=second, slot_id=str(slot["_id"]))

        await cancel_booking(db, str(leader_booking["_id"]), str(leader["_id"]), actor_id=str(admin_id))

        self.assertEqual(str(db["slots"].docs[0]["leader_user_id"]), str(second["_id"]))
        promoted = await db["bookings"].find_one({"_id": second_booking["_id"]})
        self.assertTrue(promoted["is_leader"])

    async def test_historical_booking_preserved_after_admin_cancel(self):
        slot = make_slot()
        student = make_user()
        admin_id = ObjectId()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))

        await cancel_booking(db, str(booking["_id"]), str(student["_id"]), actor_id=str(admin_id))

        stored = await db["bookings"].find_one({"_id": booking["_id"]})
        self.assertIsNotNone(stored)
        self.assertEqual(stored["status"], "cancelled")

    async def test_self_cancel_without_actor_id_is_unchanged(self):
        # actor_id omitted entirely -> must behave exactly as before this
        # change: cancelled_by defaults to the booking owner themself.
        slot = make_slot()
        student = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))

        updated = await cancel_booking(db, str(booking["_id"]), str(student["_id"]))

        self.assertEqual(str(updated["cancelled_by"]), str(student["_id"]))

    async def test_admin_force_cancel_inside_window_does_not_apply_ban(self):
        # Slot starts in 30 minutes — well inside the cancellation window —
        # so this would trigger a ban for a student self-cancel, but must
        # NOT trigger one when an admin force-cancels on the student's behalf.
        # Slot start_time/end_time are IST wall-clock, so "near" must be
        # computed in IST for the ban-window comparison to land as intended.
        near = datetime.now(IST) + timedelta(minutes=30)
        slot = make_slot(
            date=near.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc),
            start_time=near.strftime("%H:%M"),
            end_time=(near + timedelta(hours=1)).strftime("%H:%M"),
        )
        student = make_user()
        admin_id = ObjectId()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))

        updated = await cancel_booking(
            db, str(booking["_id"]), str(student["_id"]),
            actor_id=str(admin_id), apply_late_ban=False,
        )

        self.assertTrue(updated["late_cancel"])  # still recorded for history
        ban = await check_user_ban(db, student["_id"])
        self.assertIsNone(ban)

    async def test_student_self_cancel_inside_window_still_applies_ban(self):
        # Same near-start-time scenario, but via the normal self-cancel path
        # (apply_late_ban left at its default True) — existing behavior must
        # be unchanged.
        # Slot start_time/end_time are IST wall-clock, so "near" must be
        # computed in IST for the ban-window comparison to land as intended.
        near = datetime.now(IST) + timedelta(minutes=30)
        slot = make_slot(
            date=near.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc),
            start_time=near.strftime("%H:%M"),
            end_time=(near + timedelta(hours=1)).strftime("%H:%M"),
        )
        student = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))

        updated = await cancel_booking(db, str(booking["_id"]), str(student["_id"]))

        self.assertTrue(updated["late_cancel"])
        ban = await check_user_ban(db, student["_id"])
        self.assertIsNotNone(ban)


if __name__ == "__main__":
    unittest.main()
