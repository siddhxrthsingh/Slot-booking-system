from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class BookingCreate(BaseModel):
    slot_id: str
    notes: str | None = None


class BookingResponse(BaseModel):
    id: str
    slot_id: str
    sport: str
    status: Literal["confirmed", "pending_approval", "cancelled"]
    booking_date: datetime
    cancelled_at: datetime | None = None
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
