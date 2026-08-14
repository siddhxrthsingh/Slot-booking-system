from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.models.user import PyObjectId


class UserSnapshot(BaseModel):
    name: str | None = None
    srn: str | None = None
    phone: str | None = None
    branch: str | None = None
    program: str | None = None
    semester: str | None = None
    section: str | None = None
    campus: str | None = None


class BookingModel(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_id: PyObjectId
    slot_id: PyObjectId
    facility_id: PyObjectId | None = None
    sport: str
    status: Literal["confirmed", "pending_approval", "cancelled"] = "confirmed"
    booking_date: datetime = Field(default_factory=datetime.utcnow)
    joined_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_by: PyObjectId | None = None
    is_leader: bool = False
    user_snapshot: UserSnapshot | None = None
    notes: str | None = None
    approved_by: PyObjectId | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
