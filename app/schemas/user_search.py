import uuid
from datetime import date

from pydantic import BaseModel


class UserSearchItem(BaseModel):
    id: uuid.UUID
    nickname: str
    avatar_url: str | None
    gender: str
    city: str
    ntrp_level: str
    ntrp_label: str
    bio: str | None
    years_playing: int | None
    is_ideal_player: bool
    is_following: bool
    last_active_at: date | None

    model_config = {"from_attributes": True}


class UserSearchResponse(BaseModel):
    users: list[UserSearchItem]
    total: int
    page: int
    page_size: int

    model_config = {"from_attributes": True}
