from datetime import datetime
from pydantic import BaseModel, Field
from app.models.user import PyObjectId


class SessionModel(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_id: PyObjectId
    refresh_token_hash: str
    expires_at: datetime
    ip_address: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
