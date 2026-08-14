from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FacilityCreate(BaseModel):
    campus: Literal["RR"]
    sport: str
    facility_type: Literal["court", "table"]
    name: str
    display_name: str
    capacity: int
    is_active: bool = True
    sort_order: int = 0


class FacilityResponse(FacilityCreate):
    id: str
    created_at: datetime
    updated_at: datetime | None = None
