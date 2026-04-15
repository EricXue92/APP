import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EventType(str, enum.Enum):
    SINGLES_ELIMINATION = "singles_elimination"
    DOUBLES_ELIMINATION = "doubles_elimination"
    ROUND_ROBIN = "round_robin"


class EventStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EventParticipantStatus(str, enum.Enum):
    REGISTERED = "registered"
    CONFIRMED = "confirmed"
    WITHDRAWN = "withdrawn"
    ELIMINATED = "eliminated"


class EventMatchStatus(str, enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    WALKOVER = "walkover"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[EventType] = mapped_column(Enum(EventType))
    min_ntrp: Mapped[str] = mapped_column(String(10))
    max_ntrp: Mapped[str] = mapped_column(String(10))
    gender_requirement: Mapped[str] = mapped_column(String(20), default="any")
    max_participants: Mapped[int] = mapped_column(Integer)
    games_per_set: Mapped[int] = mapped_column(Integer, default=6)
    num_sets: Mapped[int] = mapped_column(Integer, default=3)
    match_tiebreak: Mapped[bool] = mapped_column(Boolean, default=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    registration_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped["User"] = relationship(foreign_keys=[creator_id])
    participants: Mapped[list["EventParticipant"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    matches: Mapped[list["EventMatch"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventParticipant(Base):
    __tablename__ = "event_participants"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_participants_event_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(10), nullable=True)
    team_name: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[EventParticipantStatus] = mapped_column(Enum(EventParticipantStatus), default=EventParticipantStatus.REGISTERED)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["Event"] = relationship(back_populates="participants", foreign_keys=[event_id])
    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class EventMatch(Base):
    __tablename__ = "event_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    round: Mapped[int] = mapped_column(Integer)
    match_order: Mapped[int] = mapped_column(Integer)
    player_a_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    player_b_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    winner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[EventMatchStatus] = mapped_column(Enum(EventMatchStatus), default=EventMatchStatus.PENDING)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["Event"] = relationship(back_populates="matches", foreign_keys=[event_id])
    player_a: Mapped["User | None"] = relationship(foreign_keys=[player_a_id])
    player_b: Mapped["User | None"] = relationship(foreign_keys=[player_b_id])
    winner: Mapped["User | None"] = relationship(foreign_keys=[winner_id])
    sets: Mapped[list["EventSet"]] = relationship(back_populates="match", cascade="all, delete-orphan")


class EventSet(Base):
    __tablename__ = "event_sets"
    __table_args__ = (UniqueConstraint("match_id", "set_number", name="uq_event_sets_match_set"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("event_matches.id", ondelete="CASCADE"))
    set_number: Mapped[int] = mapped_column(Integer)
    score_a: Mapped[int] = mapped_column(Integer)
    score_b: Mapped[int] = mapped_column(Integer)
    tiebreak_a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tiebreak_b: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match: Mapped["EventMatch"] = relationship(back_populates="sets", foreign_keys=[match_id])
