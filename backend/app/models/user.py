from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, _info=None):
        if not ObjectId.is_valid(str(v)):
            raise ValueError(f"Invalid ObjectId: {v}")
        return str(v)


class UserModel(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    srn: str
    email: str
    name: str
    program: str | None = None
    branch: str | None = None
    campus: Literal["RR", "EC"] | None = None
    role: Literal["student", "admin"] = "student"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime | None = None

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
