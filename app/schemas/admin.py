import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserRoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern=r"^(user|admin|superadmin)$")


class AdminUserListResponse(BaseModel):
    id: uuid.UUID
    nickname: str
    avatar_url: str | None
    gender: str
    city: str
    ntrp_level: str
    ntrp_label: str
    credit_score: int
    cancel_count: int
    role: str
    is_suspended: bool
    is_ideal_player: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserDetailResponse(AdminUserListResponse):
    bio: str | None
    years_playing: int | None
    language: str
    is_verified: bool
    is_active: bool
    booking_count: int
    avg_review: float | None
    updated_at: datetime


class CourtAdminResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    city: str
    latitude: float | None
    longitude: float | None
    court_type: str
    surface_type: str | None
    is_approved: bool
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardStatsResponse(BaseModel):
    total_users: int
    suspended_users: int
    pending_reports: int
    pending_courts: int
    active_bookings: int
    active_events: int


class AuditLogEntry(BaseModel):
    id: uuid.UUID
    admin_id: uuid.UUID
    action: str
    target_type: str
    target_id: uuid.UUID
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
