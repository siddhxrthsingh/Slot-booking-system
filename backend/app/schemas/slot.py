from datetime import datetime
from typing import Literal
from pydantic import BaseModel, field_validator, model_validator


class SlotCreate(BaseModel):
    sport: str
    date: datetime
    start_time: str  # "HH:MM"
    end_time: str    # "HH:MM"
    venue: str
    campus: Literal["RR", "EC"]
    capacity: int
    requires_approval: bool = False

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError("Time must be in HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time value")
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "SlotCreate":
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class SlotResponse(BaseModel):
    id: str
    facility_id: str | None = None
    facility_name: str | None = None
    sport: str
    date: datetime
    start_time: str
    end_time: str
    venue: str
    campus: str
    duration_minutes: int | None = None
    capacity: int
    booked_count: int
    available_count: int
    status: str
    slot_type: str | None = None
    is_manual: bool = False
    requires_approval: bool


class SlotFilter(BaseModel):
    sport: str | None = None
    date: datetime | None = None
    campus: Literal["RR", "EC"] | None = None
    venue: str | None = None
