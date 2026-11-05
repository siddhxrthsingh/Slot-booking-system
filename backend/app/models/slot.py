from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.models.user import PyObjectId


class SlotModel(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    facility_id: PyObjectId | None = None
    facility_name: str | None = None
    sport: str
    date: datetime
    start_time: str  # "HH:MM"
    end_time: str    # "HH:MM"
    venue: str
    campus: Literal["RR", "EC"]
    capacity: int
    booked_count: int = 0
    status: Literal["open", "full", "cancelled", "closed"] = "open"
    duration_minutes: int | None = None
    slot_type: Literal["generated", "manual", "staff", "cleaning", "lunch"] = "generated"
    requires_approval: bool = False
    leader_user_id: PyObjectId | None = None
    created_by: PyObjectId | None = None
    override_reason: str | None = None
    notes: str | None = None
    is_manual: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
