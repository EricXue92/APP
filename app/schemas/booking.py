import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


class BookingCreateRequest(BaseModel):
    court_id: uuid.UUID
    match_type: str = Field(..., pattern=r"^(singles|doubles)$")
    play_date: date
    start_time: time
    end_time: time
    min_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    max_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    gender_requirement: str = Field(default="any", pattern=r"^(male_only|female_only|any)$")
    cost_per_person: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)


class ParticipantResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    nickname: str
    status: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class BookingResponse(BaseModel):
    id: uuid.UUID
    creator_id: uuid.UUID
    court_id: uuid.UUID
    match_type: str
    play_date: date
    start_time: time
    end_time: time
    min_ntrp: str
    max_ntrp: str
    gender_requirement: str
    max_participants: int
    cost_per_person: int | None
    description: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingDetailResponse(BookingResponse):
    participants: list[ParticipantResponse]
    court_name: str


class ParticipantUpdateRequest(BaseModel):
    status: str = Field(..., pattern=r"^(accepted|rejected)$")
