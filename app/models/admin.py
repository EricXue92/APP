import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminAction(str, enum.Enum):
    USER_SUSPENDED = "user_suspended"
    USER_UNSUSPENDED = "user_unsuspended"
    USER_ROLE_CHANGED = "user_role_changed"
    USER_CREDIT_RESET = "user_credit_reset"
    COURT_APPROVED = "court_approved"
    COURT_REJECTED = "court_rejected"
    COURT_DELETED = "court_deleted"
    REPORT_RESOLVED = "report_resolved"
    BOOKING_CANCELLED = "booking_cancelled"
    EVENT_CANCELLED = "event_cancelled"
    EVENT_PARTICIPANT_REMOVED = "event_participant_removed"
    MESSAGE_DELETED = "message_deleted"


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[AdminAction] = mapped_column(Enum(AdminAction))
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
