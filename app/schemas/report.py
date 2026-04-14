import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReportCreateRequest(BaseModel):
    reported_user_id: uuid.UUID
    target_type: str = Field(..., pattern=r"^(user|review)$")
    target_id: uuid.UUID | None = None
    reason: str = Field(..., pattern=r"^(no_show|harassment|false_info|inappropriate|other)$")
    description: str | None = Field(default=None, max_length=1000)


class ReportResponse(BaseModel):
    id: uuid.UUID
    reporter_id: uuid.UUID
    reported_user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reason: str
    description: str | None
    status: str
    resolution: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportDetailResponse(ReportResponse):
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None


class ReportResolveRequest(BaseModel):
    resolution: str = Field(..., pattern=r"^(dismissed|warned|content_hidden|suspended)$")
