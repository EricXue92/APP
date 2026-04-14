import uuid
from datetime import datetime

from pydantic import BaseModel


class FollowCreateRequest(BaseModel):
    followed_id: uuid.UUID


class FollowResponse(BaseModel):
    id: uuid.UUID
    follower_id: uuid.UUID
    followed_id: uuid.UUID
    is_mutual: bool
    created_at: datetime

    model_config = {"from_attributes": True}
