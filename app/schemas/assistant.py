from pydantic import BaseModel, Field


class ParseBookingRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=500)


class ParseBookingResponse(BaseModel):
    match_type: str | None = None
    play_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    court_keyword: str | None = None
    court_id: str | None = None
    court_name: str | None = None
    min_ntrp: str | None = None
    max_ntrp: str | None = None
    gender_requirement: str | None = None
    cost_description: str | None = None
