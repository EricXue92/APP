import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    type: str = Field(..., pattern=r"^(text|image|location|booking_card)$")
    content: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    sender_id: uuid.UUID | None
    sender_nickname: str | None
    type: str
    content: str
    is_deleted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ParticipantInfo(BaseModel):
    user_id: uuid.UUID
    nickname: str
    avatar_url: str | None

    model_config = {"from_attributes": True}


class RoomResponse(BaseModel):
    id: uuid.UUID
    type: str
    name: str | None
    booking_id: uuid.UUID | None
    is_readonly: bool
    participants: list[ParticipantInfo]
    last_message: MessageResponse | None
    unread_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
