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
    IDEAL_PLAYER_GAINED = "ideal_player_gained"
    IDEAL_PLAYER_LOST = "ideal_player_lost"
    MATCH_PROPOSAL_RECEIVED = "match_proposal_received"
    MATCH_PROPOSAL_ACCEPTED = "match_proposal_accepted"
    MATCH_PROPOSAL_REJECTED = "match_proposal_rejected"
    MATCH_SUGGESTION = "match_suggestion"
    NEW_CHAT_MESSAGE = "new_chat_message"
    EVENT_REGISTRATION_OPEN = "event_registration_open"
    EVENT_JOINED = "event_joined"
    EVENT_STARTED = "event_started"
    EVENT_MATCH_READY = "event_match_ready"
    EVENT_SCORE_SUBMITTED = "event_score_submitted"
    EVENT_SCORE_CONFIRMED = "event_score_confirmed"
    EVENT_SCORE_DISPUTED = "event_score_disputed"
    EVENT_WALKOVER = "event_walkover"
    EVENT_ELIMINATED = "event_eliminated"
    EVENT_COMPLETED = "event_completed"
    EVENT_CANCELLED = "event_cancelled"
    BOOKING_INVITE_RECEIVED = "booking_invite_received"
    BOOKING_INVITE_ACCEPTED = "booking_invite_accepted"
    BOOKING_INVITE_REJECTED = "booking_invite_rejected"


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
