"""
Free Speed Plan Step 4: join/cancel confirmation emails must not sit on the
booking's critical path. The routers now hand them to FastAPI's
BackgroundTasks instead of awaiting them directly — this proves (a) the
booking/cancellation response is produced without the email call having run
yet, and (b) a failure in that deferred email call can never affect an
already-returned successful booking/cancellation.
"""
import unittest
from unittest.mock import AsyncMock

from fastapi import BackgroundTasks

from app.routers import bookings
from app.schemas.booking import BookingCreate
from app.services import email_service
from tests.test_booking_join_service import FakeDb, make_facility, make_slot, make_user


class EmailBackgroundTaskTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_confirm = email_service.send_booking_confirmation
        self._orig_cancel = email_service.send_booking_cancellation

    def tearDown(self):
        email_service.send_booking_confirmation = self._orig_confirm
        email_service.send_booking_cancellation = self._orig_cancel

    async def test_create_booking_succeeds_before_confirmation_email_runs(self):
        mock_send = AsyncMock()
        email_service.send_booking_confirmation = mock_send

        slot = make_slot()
        user = make_user(email="student@pes.edu")
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        background_tasks = BackgroundTasks()

        response = await bookings.create_booking(
            body=BookingCreate(slot_id=str(slot["_id"])),
            background_tasks=background_tasks,
            db=db,
            current_user=user,
        )

        self.assertTrue(response["status"])
        self.assertEqual(response["data"]["status"], "confirmed")
        # The route has already returned a successful booking, but the email
        # itself has not been sent yet — it's deferred.
        mock_send.assert_not_called()

        await background_tasks()
        mock_send.assert_awaited_once()

    async def test_confirmation_email_failure_does_not_affect_returned_booking(self):
        async def _raise(*args, **kwargs):
            raise RuntimeError("SMTP exploded")

        email_service.send_booking_confirmation = _raise

        slot = make_slot()
        user = make_user(email="student@pes.edu")
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        background_tasks = BackgroundTasks()

        response = await bookings.create_booking(
            body=BookingCreate(slot_id=str(slot["_id"])),
            background_tasks=background_tasks,
            db=db,
            current_user=user,
        )

        # The booking itself succeeded and was already returned...
        self.assertTrue(response["status"])
        self.assertEqual(response["data"]["status"], "confirmed")
        self.assertEqual(db["bookings"].docs[0]["status"], "confirmed")

        # ...independently of whatever the deferred email task does later.
        with self.assertRaises(RuntimeError):
            await background_tasks()
        # The booking record is unaffected by the email task's failure.
        self.assertEqual(db["bookings"].docs[0]["status"], "confirmed")

    async def test_cancel_booking_succeeds_before_cancellation_email_runs(self):
        mock_send = AsyncMock()
        email_service.send_booking_cancellation = mock_send

        slot = make_slot()
        user = make_user(email="student@pes.edu")
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        created = await bookings.create_booking(
            body=BookingCreate(slot_id=str(slot["_id"])),
            background_tasks=BackgroundTasks(),
            db=db,
            current_user=user,
        )
        booking_id = created["data"]["booking_id"]

        background_tasks = BackgroundTasks()
        response = await bookings.cancel_booking(
            booking_id=booking_id,
            background_tasks=background_tasks,
            db=db,
            current_user=user,
        )

        self.assertTrue(response["status"])
        self.assertEqual(response["data"]["status"], "cancelled")
        mock_send.assert_not_called()

        await background_tasks()
        mock_send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
