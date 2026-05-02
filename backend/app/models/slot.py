from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.models.user import PyObjectId


class SlotModel(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    sport: str
    date: datetime
    start_time: str  # "HH:MM"
    end_time: str    # "HH:MM"
    venue: str
    campus: Literal["RR", "EC"]
    capacity: int
    booked_count: int = 0
    status: Literal["open", "full", "cancelled"] = "open"
    requires_approval: bool = False
    created_by: PyObjectId | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
