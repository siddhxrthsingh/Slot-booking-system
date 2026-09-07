import unittest

from bson import ObjectId

from app.services.admin_service import get_slot_roster
from app.services.booking_service import cancel_booking, create_booking
from tests.test_booking_join_service import FakeDb, make_facility, make_slot, make_user


class SlotRosterTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_and_cancelled_participants_both_returned(self):
        slot = make_slot()
        leader = make_user()
        second = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        leader_booking = await create_booking(db, user=leader, slot_id=str(slot["_id"]))
        second_booking = await create_booking(db, user=second, slot_id=str(slot["_id"]))
        await cancel_booking(db, str(second_booking["_id"]), str(second["_id"]))

        roster = await get_slot_roster(db, str(slot["_id"]))

        statuses = {p["booking_id"]: p["status"] for p in roster["participants"]}
        self.assertEqual(len(roster["participants"]), 2)
        self.assertEqual(statuses[str(leader_booking["_id"])], "confirmed")
        self.assertEqual(statuses[str(second_booking["_id"])], "cancelled")

    async def test_participants_ordered_by_joined_at_ascending(self):
        slot = make_slot()
        first = make_user()
        second = make_user()
        third = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        b1 = await create_booking(db, user=first, slot_id=str(slot["_id"]))
        b2 = await create_booking(db, user=second, slot_id=str(slot["_id"]))
        b3 = await create_booking(db, user=third, slot_id=str(slot["_id"]))

        roster = await get_slot_roster(db, str(slot["_id"]))

        ids_in_order = [p["booking_id"] for p in roster["participants"]]
        self.assertEqual(ids_in_order, [str(b1["_id"]), str(b2["_id"]), str(b3["_id"])])

    async def test_user_snapshot_and_is_leader_are_returned(self):
        slot = make_slot()
        leader = make_user(name="Leader One", srn="PES1UG22CS999")
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        await create_booking(db, user=leader, slot_id=str(slot["_id"]))

        roster = await get_slot_roster(db, str(slot["_id"]))

        entry = roster["participants"][0]
        self.assertTrue(entry["is_leader"])
        self.assertEqual(entry["user_snapshot"]["name"], "Leader One")
        self.assertEqual(entry["user_snapshot"]["srn"], "PES1UG22CS999")

    async def test_cancelled_at_and_cancelled_by_are_preserved(self):
        slot = make_slot()
        user = make_user()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        booking = await create_booking(db, user=user, slot_id=str(slot["_id"]))
        await cancel_booking(db, str(booking["_id"]), str(user["_id"]))

        roster = await get_slot_roster(db, str(slot["_id"]))

        entry = roster["participants"][0]
        self.assertEqual(entry["status"], "cancelled")
        self.assertIsNotNone(entry["cancelled_at"])
        self.assertEqual(entry["cancelled_by"], str(user["_id"]))

    async def test_zero_bookings_returns_empty_participants_list(self):
        slot = make_slot()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        roster = await get_slot_roster(db, str(slot["_id"]))

        self.assertEqual(roster["participants"], [])
        self.assertEqual(roster["slot"]["id"], str(slot["_id"]))

    async def test_slot_identity_fields_are_included(self):
        slot = make_slot()
        db = FakeDb(slots=[slot], facilities=[make_facility(slot, 6)])

        roster = await get_slot_roster(db, str(slot["_id"]))

        slot_out = roster["slot"]
        for field in (
            "id", "facility_id", "facility_name", "sport", "date",
            "start_time", "end_time", "campus", "capacity", "booked_count",
            "status", "leader_user_id",
        ):
            self.assertIn(field, slot_out)

    async def test_nonexistent_slot_raises_lookup_error(self):
        db = FakeDb(slots=[], facilities=[])

        with self.assertRaises(LookupError):
            await get_slot_roster(db, str(ObjectId()))

    async def test_malformed_slot_id_raises_value_error(self):
        db = FakeDb(slots=[], facilities=[])

        with self.assertRaises(ValueError):
            await get_slot_roster(db, "not-a-valid-object-id")


if __name__ == "__main__":
    unittest.main()
