import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    nickname: str
    avatar_url: str | None
    gender: str
    city: str
    ntrp_level: str
    ntrp_label: str
    credit_score: int
    bio: str | None
    years_playing: int | None
    language: str
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_url: str | None = None
    city: str | None = Field(default=None, min_length=1, max_length=50)
    ntrp_level: str | None = Field(default=None, pattern=r"^\d\.\d[+-]?$")
    bio: str | None = Field(default=None, max_length=500)
    years_playing: int | None = Field(default=None, ge=0, le=80)
    language: str | None = Field(default=None, pattern=r"^(zh-Hans|zh-Hant|en)$")


class CreditScoreResponse(BaseModel):
    credit_score: int
    cancel_count: int
    attendance_rate: float | None = None
