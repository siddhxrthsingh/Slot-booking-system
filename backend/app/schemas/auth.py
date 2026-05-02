from pydantic import BaseModel, EmailStr
from typing import Literal


class LoginRequest(BaseModel):
    username: str  # SRN or email
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: str
    srn: str
    email: str
    name: str
    program: str | None = None
    branch: str | None = None
    campus: Literal["RR", "EC"] | None = None
    role: Literal["student", "admin"]


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserProfile
