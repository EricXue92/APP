import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotificationType(str, enum.Enum):
    BOOKING_JOINED = "booking_joined"
    BOOKING_ACCEPTED = "booking_accepted"
    BOOKING_REJECTED = "booking_rejected"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_COMPLETED = "booking_completed"
    NEW_FOLLOWER = "new_follower"
    NEW_MUTUAL = "new_mutual"
    REVIEW_REVEALED = "review_revealed"
    REPORT_RESOLVED = "report_resolved"
    ACCOUNT_WARNED = "account_warned"
    ACCOUNT_SUSPENDED = "account_suspended"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recipient: Mapped["User"] = relationship(foreign_keys=[recipient_id])
    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_id])
