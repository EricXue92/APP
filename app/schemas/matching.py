import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator


class TimeSlotRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: time
    end_time: time

    @field_validator("start_time", "end_time")
    @classmethod
    def must_be_half_hour(cls, v: time) -> time:
        if v.minute not in (0, 30):
            raise ValueError("Time must be on the hour or half hour")
        return v


class TimeSlotResponse(BaseModel):
    id: uuid.UUID
    day_of_week: int
    start_time: time
    end_time: time

    model_config = {"from_attributes": True}


class PreferenceCreateRequest(BaseModel):
    match_type: str = Field(default="any", pattern=r"^(singles|doubles|any)$")
    min_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    max_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    gender_preference: str = Field(default="any", pattern=r"^(male_only|female_only|any)$")
    max_distance_km: float | None = Field(default=None, ge=0)
    time_slots: list[TimeSlotRequest] = Field(..., min_length=1)
    court_ids: list[uuid.UUID] = Field(default_factory=list)


class PreferenceResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    match_type: str
    min_ntrp: str
    max_ntrp: str
    gender_preference: str
    max_distance_km: float | None
    is_active: bool
    last_active_at: datetime
    time_slots: list[TimeSlotResponse]
    court_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class ToggleResponse(BaseModel):
    is_active: bool


class CandidateResponse(BaseModel):
    user_id: uuid.UUID
    nickname: str
    gender: str
    ntrp_level: str
    ntrp_label: str
    credit_score: int
    is_ideal_player: bool
    city: str
    score: float


class BookingRecommendationResponse(BaseModel):
    booking_id: uuid.UUID
    creator_id: uuid.UUID
    creator_nickname: str
    court_id: uuid.UUID
    court_name: str
    match_type: str
    play_date: date
    start_time: time
    end_time: time
    min_ntrp: str
    max_ntrp: str
    gender_requirement: str
    score: float


class ProposalCreateRequest(BaseModel):
    target_id: uuid.UUID
    court_id: uuid.UUID
    match_type: str = Field(default="singles", pattern=r"^(singles|doubles)$")
    play_date: date
    start_time: time
    end_time: time
    message: str | None = Field(default=None, max_length=500)


class ProposalResponse(BaseModel):
    id: uuid.UUID
    proposer_id: uuid.UUID
    proposer_nickname: str
    target_id: uuid.UUID
    target_nickname: str
    court_id: uuid.UUID
    court_name: str
    match_type: str
    play_date: date
    start_time: time
    end_time: time
    message: str | None
    status: str
    created_at: datetime
    responded_at: datetime | None


class ProposalRespondRequest(BaseModel):
    status: str = Field(..., pattern=r"^(accepted|rejected)$")
