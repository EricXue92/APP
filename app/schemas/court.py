import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CourtCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    address: str = Field(..., min_length=1, max_length=255)
    city: str = Field(..., min_length=1, max_length=50)
    latitude: float | None = None
    longitude: float | None = None
    court_type: str = Field(..., pattern=r"^(indoor|outdoor)$")
    surface_type: str | None = Field(default=None, pattern=r"^(hard|clay|grass)$")


class CourtResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    city: str
    latitude: float | None
    longitude: float | None
    court_type: str
    surface_type: str | None
    is_approved: bool
    created_at: datetime

    model_config = {"from_attributes": True}
