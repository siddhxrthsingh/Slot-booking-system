from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.models.user import PyObjectId


class BookingModel(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_id: PyObjectId
    slot_id: PyObjectId
    sport: str
    status: Literal["confirmed", "pending_approval", "cancelled"] = "confirmed"
    booking_date: datetime = Field(default_factory=datetime.utcnow)
    cancelled_at: datetime | None = None
    notes: str | None = None
    approved_by: PyObjectId | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
