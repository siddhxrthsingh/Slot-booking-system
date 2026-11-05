import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.routers import admin as admin_router
from app.services.booking_service import create_booking
from tests.test_booking_join_service import FakeDb, make_facility, make_slot, make_user


class AdminOccupancyBroadcastTests(unittest.IsolatedAsyncioTestCase):
    """Phase 8.3: admin-triggered cancellations must broadcast the affected
    slot's latest occupancy via ws_manager.broadcast_occupancy, using the
    same occupancy_update payload shape as student cancellation."""

    async def test_admin_cancel_booking_broadcasts_occupancy_after_db_update(self):
        slot = make_slot()
        student = make_user()
        admin = {"_id": ObjectId()}
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        booking = await create_booking(db, user=student, slot_id=str(slot["_id"]))

        with patch.object(admin_router.ws_manager, "broadcast", new=AsyncMock()), \
             patch.object(admin_router.ws_manager, "broadcast_occupancy", new=AsyncMock()) as mock_occ:
            await admin_router.admin_cancel_booking(str(booking["_id"]), db, admin)

        mock_occ.assert_awaited_once()
        slot_id_arg, payload = mock_occ.await_args.args
        self.assertEqual(slot_id_arg, str(slot["_id"]))
        self.assertEqual(payload["booked_count"], 0)
        self.assertEqual(payload["available_count"], payload["capacity"])
        self.assertEqual(payload["status"], "open")

        # Broadcast payload must reflect DB state actually written.
        stored_slot = await db["slots"].find_one({"_id": slot["_id"]})
        self.assertEqual(payload["booked_count"], stored_slot["booked_count"])

    async def test_admin_cancel_slot_broadcasts_final_occupancy_and_status(self):
        slot = make_slot()
        student = make_user()
        admin = {"_id": ObjectId()}
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])
        await create_booking(db, user=student, slot_id=str(slot["_id"]))

        with patch.object(admin_router.ws_manager, "broadcast", new=AsyncMock()), \
             patch.object(admin_router.ws_manager, "broadcast_occupancy", new=AsyncMock()) as mock_occ:
            await admin_router.cancel_slot(str(slot["_id"]), db, admin)

        mock_occ.assert_awaited_once()
        slot_id_arg, payload = mock_occ.await_args.args
        self.assertEqual(slot_id_arg, str(slot["_id"]))
        self.assertEqual(payload["status"], "cancelled")
        self.assertEqual(payload["booked_count"], 0)

        stored_slot = await db["slots"].find_one({"_id": slot["_id"]})
        self.assertEqual(payload["status"], stored_slot["status"])


if __name__ == "__main__":
    unittest.main()
