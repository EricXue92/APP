import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreateRequest(BaseModel):
    booking_id: uuid.UUID
    reviewee_id: uuid.UUID
    skill_rating: int = Field(..., ge=1, le=5)
    punctuality_rating: int = Field(..., ge=1, le=5)
    sportsmanship_rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class ReviewResponse(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewee_id: uuid.UUID
    reviewer_nickname: str
    skill_rating: int
    punctuality_rating: int
    sportsmanship_rating: int
    comment: str | None
    is_revealed: bool
    created_at: datetime


class UserReviewSummary(BaseModel):
    average_skill: float
    average_punctuality: float
    average_sportsmanship: float
    total_reviews: int
    reviews: list[ReviewResponse]


class PendingReviewItem(BaseModel):
    booking_id: uuid.UUID
    court_name: str
    play_date: str
    reviewees: list[dict]
    window_closes_at: datetime
