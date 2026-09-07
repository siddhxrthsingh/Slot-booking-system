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


def _validate_periods_no_overlap(periods: list[SchedulePeriodSchema]) -> list[SchedulePeriodSchema]:
    sorted_periods = sorted(periods, key=lambda p: p.start_time)
    for prev, cur in zip(sorted_periods, sorted_periods[1:]):
        if cur.start_time < prev.end_time:
            raise ValueError("Periods must not overlap within a template")
    return periods


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

    @field_validator("periods")
    @classmethod
    def periods_no_overlap(cls, value: list[SchedulePeriodSchema]) -> list[SchedulePeriodSchema]:
        return _validate_periods_no_overlap(value)

    @model_validator(mode="after")
    def facility_scope_requires_facility_id(self) -> "ScheduleTemplateCreate":
        if self.facility_scope == "facility" and not self.facility_id:
            raise ValueError("facility_id is required when facility_scope is 'facility'")
        return self


class ScheduleTemplateUpdate(BaseModel):
    """Partial update — every field optional; only supplied fields are applied."""
    sport: str | None = None
    facility_id: str | None = None
    facility_name: str | None = None
    facility_scope: Literal["sport", "facility"] | None = None
    day_type: Literal["weekday", "saturday", "sunday"] | None = None
    periods: list[SchedulePeriodSchema] | None = None
    is_active: bool | None = None
    priority: int | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    notes: str | None = None

    @field_validator("periods")
    @classmethod
    def periods_no_overlap(cls, value: list[SchedulePeriodSchema] | None) -> list[SchedulePeriodSchema] | None:
        if value is None:
            return value
        return _validate_periods_no_overlap(value)


class ScheduleTemplateResponse(ScheduleTemplateCreate):
    id: str
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
