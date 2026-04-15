import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class EventCreateRequest(BaseModel):
    name: str = Field(..., max_length=100)
    event_type: str = Field(..., pattern=r"^(singles_elimination|doubles_elimination|round_robin)$")
    min_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    max_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    gender_requirement: str = Field(default="any", pattern=r"^(male_only|female_only|any)$")
    max_participants: int = Field(..., ge=3, le=64)
    games_per_set: int = Field(default=6, ge=4, le=6)
    num_sets: int = Field(default=3, ge=1, le=3)
    match_tiebreak: bool = Field(default=False)
    start_date: date | None = None
    end_date: date | None = None
    registration_deadline: datetime
    entry_fee: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=1000)


class EventUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    max_participants: int | None = Field(default=None, ge=3, le=64)
    games_per_set: int | None = Field(default=None, ge=4, le=6)
    num_sets: int | None = Field(default=None, ge=1, le=3)
    match_tiebreak: bool | None = None
    start_date: date | None = None
    end_date: date | None = None
    registration_deadline: datetime | None = None
    entry_fee: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=1000)


class EventParticipantResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    nickname: str
    ntrp_level: str
    seed: int | None
    group_name: str | None
    team_name: str | None
    status: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    id: uuid.UUID
    creator_id: uuid.UUID
    name: str
    event_type: str
    min_ntrp: str
    max_ntrp: str
    gender_requirement: str
    max_participants: int
    games_per_set: int
    num_sets: int
    match_tiebreak: bool
    start_date: date | None
    end_date: date | None
    registration_deadline: datetime
    entry_fee: int | None
    description: str | None
    status: str
    participant_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EventDetailResponse(EventResponse):
    participants: list[EventParticipantResponse]


class EventSetResponse(BaseModel):
    set_number: int
    score_a: int
    score_b: int
    tiebreak_a: int | None
    tiebreak_b: int | None

    model_config = {"from_attributes": True}


class EventMatchResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    round: int
    match_order: int
    player_a_id: uuid.UUID | None
    player_b_id: uuid.UUID | None
    winner_id: uuid.UUID | None
    group_name: str | None
    status: str
    submitted_by: uuid.UUID | None
    confirmed_at: datetime | None
    sets: list[EventSetResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class ScoreSubmitRequest(BaseModel):
    sets: list["SetScoreInput"]


class SetScoreInput(BaseModel):
    set_number: int = Field(..., ge=1, le=3)
    score_a: int = Field(..., ge=0)
    score_b: int = Field(..., ge=0)
    tiebreak_a: int | None = None
    tiebreak_b: int | None = None


class StandingsEntry(BaseModel):
    user_id: uuid.UUID
    nickname: str
    group_name: str
    wins: int
    losses: int
    points: int
    sets_won: int
    sets_lost: int
