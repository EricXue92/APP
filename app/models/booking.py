import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MatchType(str, enum.Enum):
    SINGLES = "singles"
    DOUBLES = "doubles"


class GenderRequirement(str, enum.Enum):
    MALE_ONLY = "male_only"
    FEMALE_ONLY = "female_only"
    ANY = "any"


class BookingStatus(str, enum.Enum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ParticipantStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    court_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courts.id", ondelete="CASCADE"))
    match_type: Mapped[MatchType] = mapped_column(Enum(MatchType))
    play_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    min_ntrp: Mapped[str] = mapped_column(String(10))
    max_ntrp: Mapped[str] = mapped_column(String(10))
    gender_requirement: Mapped[GenderRequirement] = mapped_column(Enum(GenderRequirement), default=GenderRequirement.ANY)
    max_participants: Mapped[int] = mapped_column(Integer)
    cost_per_person: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.OPEN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped["User"] = relationship(foreign_keys=[creator_id])
    court: Mapped["Court"] = relationship(foreign_keys=[court_id])
    participants: Mapped[list["BookingParticipant"]] = relationship(back_populates="booking", cascade="all, delete-orphan")


class BookingParticipant(Base):
    __tablename__ = "booking_participants"
    __table_args__ = (UniqueConstraint("booking_id", "user_id", name="uq_booking_participants_booking_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[ParticipantStatus] = mapped_column(Enum(ParticipantStatus), default=ParticipantStatus.PENDING)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    booking: Mapped["Booking"] = relationship(back_populates="participants", foreign_keys=[booking_id])
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
