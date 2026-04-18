import uuid
from datetime import date

from pydantic import BaseModel


class CourtStats(BaseModel):
    court_id: uuid.UUID
    court_name: str
    match_count: int

    model_config = {"from_attributes": True}


class PartnerStats(BaseModel):
    user_id: uuid.UUID
    nickname: str
    avatar_url: str | None
    match_count: int

    model_config = {"from_attributes": True}


class UserStats(BaseModel):
    total_matches: int
    monthly_matches: int
    singles_count: int
    doubles_count: int
    top_courts: list[CourtStats]
    top_partners: list[PartnerStats]

    model_config = {"from_attributes": True}


class CalendarParticipant(BaseModel):
    user_id: uuid.UUID
    nickname: str

    model_config = {"from_attributes": True}


class CalendarBooking(BaseModel):
    booking_id: uuid.UUID
    court_name: str
    match_type: str
    start_time: str
    end_time: str
    participants: list[CalendarParticipant]

    model_config = {"from_attributes": True}


class CalendarDate(BaseModel):
    date: date
    bookings: list[CalendarBooking]

    model_config = {"from_attributes": True}


class UserCalendar(BaseModel):
    year: int
    month: int
    match_dates: list[CalendarDate]

    model_config = {"from_attributes": True}
