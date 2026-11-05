from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.user import PyObjectId


class FacilityModel(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    campus: Literal["RR"]
    sport: str
    facility_type: Literal["court", "table"]
    name: str
    display_name: str
    capacity: int
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
