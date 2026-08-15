import unittest
from datetime import datetime, timezone

from bson import ObjectId

from app.models.booking import BookingModel, UserSnapshot
from app.models.slot import SlotModel
from app.schemas.booking import BookingResponse, UserSnapshotSchema
from app.schemas.slot import SlotResponse


def now():
    return datetime.now(timezone.utc)


class ParticipationModelTests(unittest.TestCase):
    def test_booking_model_supports_participation_fields(self):
        user_id = ObjectId()
        slot_id = ObjectId()
        facility_id = ObjectId()
        cancelled_by = ObjectId()
        snapshot = {
            "name": "Student One",
            "srn": "PES1UG22CS001",
            "phone": "9999999999",
            "branch": "CSE",
            "program": "B.Tech",
            "semester": "6",
            "section": "A",
            "campus": "RR",
        }

        booking = BookingModel(
            user_id=user_id,
            slot_id=slot_id,
            facility_id=facility_id,
            sport="Badminton",
            joined_at=now(),
            cancelled_by=cancelled_by,
            is_leader=True,
            user_snapshot=UserSnapshot(**snapshot),
        )

        self.assertEqual(booking.user_id, str(user_id))
        self.assertEqual(booking.slot_id, str(slot_id))
        self.assertEqual(booking.facility_id, str(facility_id))
        self.assertEqual(booking.cancelled_by, str(cancelled_by))
        self.assertTrue(booking.is_leader)
        self.assertEqual(booking.user_snapshot.phone, "9999999999")
        self.assertEqual(booking.user_snapshot.semester, "6")
        self.assertEqual(booking.user_snapshot.section, "A")

    def test_booking_response_schema_supports_participation_fields(self):
        response = BookingResponse(
            id="booking-1",
            user_id="user-1",
            slot_id="slot-1",
            facility_id="facility-1",
            sport="Badminton",
            status="confirmed",
            booking_date=now(),
            joined_at=now(),
            cancelled_by="admin-1",
            is_leader=True,
            user_snapshot=UserSnapshotSchema(
                name="Student One",
                srn="PES1UG22CS001",
                phone="9999999999",
                branch="CSE",
                program="B.Tech",
                semester="6",
                section="A",
                campus="RR",
            ),
            created_at=now(),
        )

        self.assertEqual(response.facility_id, "facility-1")
        self.assertTrue(response.is_leader)
        self.assertEqual(response.user_snapshot.campus, "RR")

    def test_slot_model_and_schema_support_leader_count_and_capacity(self):
        leader_id = ObjectId()
        slot = SlotModel(
            sport="Badminton",
            date=now(),
            start_time="09:00",
            end_time="10:00",
            venue="Badminton Court 1",
            campus="RR",
            capacity=6,
            booked_count=3,
            leader_user_id=leader_id,
        )

        self.assertEqual(slot.capacity, 6)
        self.assertEqual(slot.booked_count, 3)
        self.assertEqual(slot.leader_user_id, str(leader_id))

        response = SlotResponse(
            id="slot-1",
            sport="Badminton",
            date=now(),
            start_time="09:00",
            end_time="10:00",
            venue="Badminton Court 1",
            campus="RR",
            capacity=6,
            booked_count=3,
            available_count=3,
            status="open",
            leader_user_id=str(leader_id),
            requires_approval=False,
        )

        self.assertEqual(response.capacity, 6)
        self.assertEqual(response.booked_count, 3)
        self.assertEqual(response.leader_user_id, str(leader_id))

    def test_existing_minimal_booking_response_remains_compatible(self):
        response = BookingResponse(
            id="booking-1",
            slot_id="slot-1",
            sport="Badminton",
            status="confirmed",
            booking_date=now(),
            created_at=now(),
        )

        self.assertIsNone(response.user_id)
        self.assertIsNone(response.facility_id)
        self.assertFalse(response.is_leader)


if __name__ == "__main__":
    unittest.main()
