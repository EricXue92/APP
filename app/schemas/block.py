import uuid
from datetime import datetime

from pydantic import BaseModel


class BlockCreateRequest(BaseModel):
    blocked_id: uuid.UUID


class BlockResponse(BaseModel):
    id: uuid.UUID
    blocker_id: uuid.UUID
    blocked_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
