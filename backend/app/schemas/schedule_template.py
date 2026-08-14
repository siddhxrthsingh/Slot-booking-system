from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class SchedulePeriodSchema(BaseModel):
    start_time: str
    end_time: str
    period_type: Literal["student", "staff", "cleaning", "lunch"]
    duration_minutes: int = 60
    is_bookable: bool
    label: str | None = None
    notes: str | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("Time must be in HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time value")
        return value

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("duration_minutes must be positive")
        return value

    @model_validator(mode="after")
    def end_after_start(self) -> "SchedulePeriodSchema":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ScheduleTemplateCreate(BaseModel):
    campus: Literal["RR"]
    sport: str
    facility_id: str | None = None
    facility_name: str | None = None
    facility_scope: Literal["sport", "facility"]
    day_type: Literal["weekday", "saturday", "sunday"]
    periods: list[SchedulePeriodSchema]
    is_active: bool = True
    priority: int = 0
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    notes: str | None = None


class ScheduleTemplateResponse(ScheduleTemplateCreate):
    id: str
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
