import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DeviceTokenCreate(BaseModel):
    platform: str = Field(..., pattern="^(ios|android)$")
    token: str = Field(..., min_length=1, max_length=4096)


class DeviceTokenResponse(BaseModel):
    id: uuid.UUID
    platform: str
    token: str
    created_at: datetime

    model_config = {"from_attributes": True}
