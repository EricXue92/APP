import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MatchTypePreference(str, enum.Enum):
    SINGLES = "singles"
    DOUBLES = "doubles"
    ANY = "any"


class GenderPreference(str, enum.Enum):
    MALE_ONLY = "male_only"
    FEMALE_ONLY = "female_only"
    ANY = "any"


class ProposalStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MatchPreference(Base):
    __tablename__ = "match_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    match_type: Mapped[MatchTypePreference] = mapped_column(Enum(MatchTypePreference), default=MatchTypePreference.ANY)
    min_ntrp: Mapped[str] = mapped_column(String(10))
    max_ntrp: Mapped[str] = mapped_column(String(10))
    gender_preference: Mapped[GenderPreference] = mapped_column(Enum(GenderPreference), default=GenderPreference.ANY)
    max_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    time_slots: Mapped[list["MatchTimeSlot"]] = relationship(
        back_populates="preference", cascade="all, delete-orphan"
    )
    preferred_courts: Mapped[list["MatchPreferenceCourt"]] = relationship(
        back_populates="preference", cascade="all, delete-orphan"
    )


class MatchTimeSlot(Base):
    __tablename__ = "match_time_slots"
    __table_args__ = (
        UniqueConstraint("preference_id", "day_of_week", "start_time", name="uq_match_time_slot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    preference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_preferences.id", ondelete="CASCADE")
    )
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Monday ... 6=Sunday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    preference: Mapped["MatchPreference"] = relationship(back_populates="time_slots")


class MatchPreferenceCourt(Base):
    __tablename__ = "match_preference_courts"
    __table_args__ = (
        UniqueConstraint("preference_id", "court_id", name="uq_match_preference_court"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    preference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_preferences.id", ondelete="CASCADE")
    )
    court_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courts.id", ondelete="CASCADE")
    )

    preference: Mapped["MatchPreference"] = relationship(back_populates="preferred_courts")
    court: Mapped["Court"] = relationship(foreign_keys=[court_id])


class MatchProposal(Base):
    __tablename__ = "match_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    court_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courts.id", ondelete="CASCADE"))
    match_type: Mapped[str] = mapped_column(String(10))  # "singles" or "doubles"
    play_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    proposer: Mapped["User"] = relationship(foreign_keys=[proposer_id])
    target: Mapped["User"] = relationship(foreign_keys=[target_id])
    court: Mapped["Court"] = relationship(foreign_keys=[court_id])
