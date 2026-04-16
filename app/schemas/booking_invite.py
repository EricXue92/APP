import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


class BookingInviteCreateRequest(BaseModel):
    invitee_id: uuid.UUID
    court_id: uuid.UUID
    match_type: str = Field(..., pattern=r"^(singles|doubles)$")
    play_date: date
    start_time: time
    end_time: time
    gender_requirement: str = Field(default="any", pattern=r"^(male_only|female_only|any)$")
    cost_per_person: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)


class BookingInviteResponse(BaseModel):
    id: uuid.UUID
    inviter_id: uuid.UUID
    invitee_id: uuid.UUID
    court_id: uuid.UUID
    match_type: str
    play_date: date
    start_time: time
    end_time: time
    gender_requirement: str
    cost_per_person: int | None
    description: str | None
    status: str
    booking_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
