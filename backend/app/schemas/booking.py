from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class BookingCreate(BaseModel):
    slot_id: str
    notes: str | None = None


class UserSnapshotSchema(BaseModel):
    name: str | None = None
    srn: str | None = None
    phone: str | None = None
    branch: str | None = None
    program: str | None = None
    semester: str | None = None
    section: str | None = None
    campus: str | None = None


class BookingResponse(BaseModel):
    id: str
    user_id: str | None = None
    slot_id: str
    facility_id: str | None = None
    sport: str
    status: Literal["confirmed", "pending_approval", "cancelled"]
    booking_date: datetime
    joined_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_by: str | None = None
    is_leader: bool = False
    user_snapshot: UserSnapshotSchema | None = None
    notes: str | None = None
    created_at: datetime


class BookingWithSlot(BookingResponse):
    slot_date: datetime | None = None
    slot_start_time: str | None = None
    slot_end_time: str | None = None
    slot_venue: str | None = None
    slot_campus: str | None = None


class ApprovalAction(BaseModel):
    action: Literal["approve", "reject"]
    notes: str | None = None
