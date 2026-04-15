import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Text, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RoomType(str, enum.Enum):
    PRIVATE = "private"
    GROUP = "group"


class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    LOCATION = "location"
    BOOKING_CARD = "booking_card"


class ChatRoom(Base):
    __tablename__ = "chat_rooms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[RoomType] = mapped_column(Enum(RoomType))
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_readonly: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participants: Mapped[list["ChatParticipant"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="room", cascade="all, delete-orphan")


class ChatParticipant(Base):
    __tablename__ = "chat_participants"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_chat_participants_room_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_rooms.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    room: Mapped["ChatRoom"] = relationship(back_populates="participants", foreign_keys=[room_id])
    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_room_created", "room_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_rooms.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[MessageType] = mapped_column(Enum(MessageType))
    content: Mapped[str] = mapped_column(Text)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("clock_timestamp()"))

    room: Mapped["ChatRoom"] = relationship(back_populates="messages", foreign_keys=[room_id])
    sender: Mapped["User | None"] = relationship(foreign_keys=[sender_id])
