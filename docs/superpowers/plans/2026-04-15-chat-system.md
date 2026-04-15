# Chat System (聊天系统) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real-time chat system where confirmed booking participants communicate via WebSocket and REST endpoints.

**Architecture:** Single-process WebSocket in the existing FastAPI monolith. Chat rooms auto-created on booking confirmation. Messages persisted to PostgreSQL. In-memory `ConnectionManager` for WebSocket connections. Sensitive word filtering via keyword blocklist. REST fallback for offline clients.

**Tech Stack:** FastAPI WebSocket, SQLAlchemy async, PostgreSQL, Pydantic v2

---

### Task 1: Models + Enums + Migration

**Files:**
- Create: `app/models/chat.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/notification.py`

- [ ] **Step 1: Create chat models**

Create `app/models/chat.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Text, String, UniqueConstraint, func
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped["ChatRoom"] = relationship(back_populates="messages", foreign_keys=[room_id])
    sender: Mapped["User | None"] = relationship(foreign_keys=[sender_id])
```

- [ ] **Step 2: Update models __init__.py**

In `app/models/__init__.py`, add the new imports:

```python
from app.models.chat import ChatRoom, ChatParticipant, Message
```

And add `"ChatRoom", "ChatParticipant", "Message"` to the `__all__` list.

- [ ] **Step 3: Add NEW_CHAT_MESSAGE notification type**

In `app/models/notification.py`, add to the `NotificationType` enum after `MATCH_SUGGESTION`:

```python
    NEW_CHAT_MESSAGE = "new_chat_message"
```

- [ ] **Step 4: Generate and run Alembic migration**

```bash
uv run alembic revision --autogenerate -m "add chat tables and new_chat_message notification type"
uv run alembic upgrade head
```

- [ ] **Step 5: Commit**

```bash
git add app/models/chat.py app/models/__init__.py app/models/notification.py alembic/versions/
git commit -m "feat(chat): add ChatRoom, ChatParticipant, Message models and migration"
```

---

### Task 2: Schemas

**Files:**
- Create: `app/schemas/chat.py`

- [ ] **Step 1: Create chat schemas**

Create `app/schemas/chat.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    type: str = Field(..., pattern=r"^(text|image|location|booking_card)$")
    content: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    sender_id: uuid.UUID | None
    sender_nickname: str | None
    type: str
    content: str
    is_deleted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ParticipantInfo(BaseModel):
    user_id: uuid.UUID
    nickname: str
    avatar_url: str | None

    model_config = {"from_attributes": True}


class RoomResponse(BaseModel):
    id: uuid.UUID
    type: str
    name: str | None
    booking_id: uuid.UUID | None
    is_readonly: bool
    participants: list[ParticipantInfo]
    last_message: MessageResponse | None
    unread_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/chat.py
git commit -m "feat(chat): add chat request/response schemas"
```

---

### Task 3: Sensitive Word Filter + Blocked Words File

**Files:**
- Create: `app/data/blocked_words.txt`
- Create: `app/services/word_filter.py`
- Create: `tests/test_word_filter.py`

- [ ] **Step 1: Create the blocked words file**

Create `app/data/blocked_words.txt` with a few sample entries (one word per line):

```
傻逼
操你妈
fuck you
shit
asshole
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_word_filter.py`:

```python
import pytest

from app.services.word_filter import contains_blocked_word, load_blocked_words


def test_load_blocked_words():
    words = load_blocked_words()
    assert isinstance(words, list)
    assert len(words) > 0


def test_contains_blocked_word_match():
    assert contains_blocked_word("you are 傻逼") is True


def test_contains_blocked_word_clean():
    assert contains_blocked_word("nice game today") is False


def test_contains_blocked_word_empty():
    assert contains_blocked_word("") is False


def test_contains_blocked_word_case_insensitive():
    assert contains_blocked_word("FUCK YOU buddy") is True
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/test_word_filter.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Write the implementation**

Create `app/services/word_filter.py`:

```python
from pathlib import Path

_BLOCKED_WORDS: list[str] = []


def load_blocked_words() -> list[str]:
    global _BLOCKED_WORDS
    if _BLOCKED_WORDS:
        return _BLOCKED_WORDS
    words_file = Path(__file__).parent.parent / "data" / "blocked_words.txt"
    if words_file.exists():
        _BLOCKED_WORDS = [
            line.strip().lower()
            for line in words_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return _BLOCKED_WORDS


def contains_blocked_word(content: str) -> bool:
    if not content:
        return False
    words = load_blocked_words()
    content_lower = content.lower()
    return any(word in content_lower for word in words)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_word_filter.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/data/blocked_words.txt app/services/word_filter.py tests/test_word_filter.py
git commit -m "feat(chat): add sensitive word filter with keyword blocklist"
```

---

### Task 4: Chat Service — Room CRUD

**Files:**
- Create: `app/services/chat.py`
- Create: `tests/test_chat.py`

- [ ] **Step 1: Write failing tests for room creation and queries**

Create `tests/test_chat.py`:

```python
import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, MatchType, GenderRequirement, ParticipantStatus
from app.models.chat import ChatRoom, RoomType
from app.models.court import Court, CourtType
from app.models.user import User, Gender
from app.services.chat import create_chat_room, get_rooms_for_user, get_room_by_id, add_participant, remove_participant, set_room_readonly


async def _create_user(session: AsyncSession, nickname: str) -> User:
    user = User(
        nickname=nickname,
        gender=Gender.MALE,
        city="Hong Kong",
        ntrp_level="3.5",
        ntrp_label="3.5 中級",
    )
    session.add(user)
    await session.flush()
    return user


async def _create_court(session: AsyncSession) -> Court:
    court = Court(
        name="Victoria Park",
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.flush()
    return court


async def _create_confirmed_booking(session: AsyncSession, creator: User, other: User, court: Court) -> Booking:
    booking = Booking(
        creator_id=creator.id,
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=date.today() + timedelta(days=7),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        gender_requirement=GenderRequirement.ANY,
        max_participants=2,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    await session.flush()
    for user in [creator, other]:
        p = BookingParticipant(booking_id=booking.id, user_id=user.id, status=ParticipantStatus.ACCEPTED)
        session.add(p)
    await session.flush()
    return booking


@pytest.mark.asyncio
async def test_create_chat_room_private(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    room = await create_chat_room(
        session,
        booking=booking,
        participant_ids=[user1.id, user2.id],
        court_name=court.name,
    )
    assert room.type == RoomType.PRIVATE
    assert room.booking_id == booking.id
    assert room.name is None
    assert len(room.participants) == 2


@pytest.mark.asyncio
async def test_create_chat_room_group(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    user3 = await _create_user(session, "Carol")
    court = await _create_court(session)

    booking = Booking(
        creator_id=user1.id,
        court_id=court.id,
        match_type=MatchType.DOUBLES,
        play_date=date.today() + timedelta(days=7),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        gender_requirement=GenderRequirement.ANY,
        max_participants=4,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    await session.flush()
    for user in [user1, user2, user3]:
        p = BookingParticipant(booking_id=booking.id, user_id=user.id, status=ParticipantStatus.ACCEPTED)
        session.add(p)
    await session.flush()

    room = await create_chat_room(
        session,
        booking=booking,
        participant_ids=[user1.id, user2.id, user3.id],
        court_name=court.name,
    )
    assert room.type == RoomType.GROUP
    assert room.name is not None
    assert "Victoria Park" in room.name
    assert len(room.participants) == 3


@pytest.mark.asyncio
async def test_get_rooms_for_user(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)
    rooms = await get_rooms_for_user(session, user1.id)
    assert len(rooms) == 1
    assert rooms[0].booking_id == booking.id


@pytest.mark.asyncio
async def test_set_room_readonly(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)
    assert room.is_readonly is False

    await set_room_readonly(session, booking_id=booking.id)
    await session.refresh(room)
    assert room.is_readonly is True


@pytest.mark.asyncio
async def test_add_remove_participant(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    user3 = await _create_user(session, "Carol")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)
    assert len(room.participants) == 2

    await add_participant(session, room_id=room.id, user_id=user3.id)
    await session.refresh(room)
    room = await get_room_by_id(session, room.id)
    assert len(room.participants) == 3

    await remove_participant(session, room_id=room.id, user_id=user3.id)
    room = await get_room_by_id(session, room.id)
    assert len(room.participants) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_chat.py -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the chat service (room CRUD)**

Create `app/services/chat.py`:

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, MatchType
from app.models.chat import ChatParticipant, ChatRoom, Message, MessageType, RoomType


async def create_chat_room(
    session: AsyncSession,
    *,
    booking: Booking,
    participant_ids: list[uuid.UUID],
    court_name: str,
) -> ChatRoom:
    is_private = booking.match_type == MatchType.SINGLES
    room_type = RoomType.PRIVATE if is_private else RoomType.GROUP

    name = None
    if room_type == RoomType.GROUP:
        date_str = booking.play_date.strftime("%-m/%-d")
        name = f"雙打 @ {court_name} {date_str}"

    room = ChatRoom(
        type=room_type,
        booking_id=booking.id,
        name=name,
    )
    session.add(room)
    await session.flush()

    for uid in participant_ids:
        participant = ChatParticipant(room_id=room.id, user_id=uid)
        session.add(participant)
    await session.flush()

    await session.refresh(room)
    room = await get_room_by_id(session, room.id)
    return room


async def get_room_by_id(session: AsyncSession, room_id: uuid.UUID) -> ChatRoom | None:
    result = await session.execute(
        select(ChatRoom)
        .options(
            selectinload(ChatRoom.participants).selectinload(ChatParticipant.user),
        )
        .where(ChatRoom.id == room_id)
    )
    return result.scalar_one_or_none()


async def get_room_by_booking_id(session: AsyncSession, booking_id: uuid.UUID) -> ChatRoom | None:
    result = await session.execute(
        select(ChatRoom)
        .options(
            selectinload(ChatRoom.participants).selectinload(ChatParticipant.user),
        )
        .where(ChatRoom.booking_id == booking_id)
    )
    return result.scalar_one_or_none()


async def get_rooms_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[ChatRoom]:
    result = await session.execute(
        select(ChatRoom)
        .join(ChatParticipant, ChatParticipant.room_id == ChatRoom.id)
        .options(
            selectinload(ChatRoom.participants).selectinload(ChatParticipant.user),
        )
        .where(ChatParticipant.user_id == user_id)
        .order_by(ChatRoom.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def set_room_readonly(session: AsyncSession, *, booking_id: uuid.UUID) -> None:
    room = await get_room_by_booking_id(session, booking_id)
    if room:
        room.is_readonly = True
        await session.flush()


async def add_participant(session: AsyncSession, *, room_id: uuid.UUID, user_id: uuid.UUID) -> ChatParticipant:
    participant = ChatParticipant(room_id=room_id, user_id=user_id)
    session.add(participant)
    await session.flush()
    return participant


async def remove_participant(session: AsyncSession, *, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
    result = await session.execute(
        select(ChatParticipant).where(
            ChatParticipant.room_id == room_id,
            ChatParticipant.user_id == user_id,
        )
    )
    participant = result.scalar_one_or_none()
    if participant:
        await session.delete(participant)
        await session.flush()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_chat.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat.py tests/test_chat.py
git commit -m "feat(chat): add chat service with room CRUD operations"
```

---

### Task 5: Chat Service — Messaging (send, history, mark read)

**Files:**
- Modify: `app/services/chat.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Write failing tests for messaging**

Append to `tests/test_chat.py`:

```python
from app.services.chat import send_message, get_messages, mark_room_read, get_unread_count


@pytest.mark.asyncio
async def test_send_message(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    msg = await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="Hello!")
    assert msg.content == "Hello!"
    assert msg.sender_id == user1.id
    assert msg.room_id == room.id


@pytest.mark.asyncio
async def test_send_message_blocked_word(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    with pytest.raises(ValueError, match="blocked"):
        await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="你是傻逼")


@pytest.mark.asyncio
async def test_send_message_readonly_room(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    await set_room_readonly(session, booking_id=booking.id)
    with pytest.raises(ValueError, match="read-only"):
        await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="Hi")


@pytest.mark.asyncio
async def test_send_message_not_participant(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    user3 = await _create_user(session, "Carol")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    with pytest.raises(PermissionError):
        await send_message(session, room_id=room.id, sender_id=user3.id, type="text", content="Hi")


@pytest.mark.asyncio
async def test_get_messages_pagination(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    for i in range(5):
        await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content=f"msg {i}")

    messages = await get_messages(session, room_id=room.id, limit=3)
    assert len(messages) == 3
    # Most recent first
    assert messages[0].content == "msg 4"

    # Cursor pagination: get messages before the oldest in first page
    older = await get_messages(session, room_id=room.id, before_id=messages[-1].id, limit=3)
    assert len(older) == 2
    assert older[0].content == "msg 1"


@pytest.mark.asyncio
async def test_unread_count_and_mark_read(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="Hello")
    await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="World")

    count = await get_unread_count(session, room_id=room.id, user_id=user2.id)
    assert count == 2

    await mark_room_read(session, room_id=room.id, user_id=user2.id)
    count = await get_unread_count(session, room_id=room.id, user_id=user2.id)
    assert count == 0


@pytest.mark.asyncio
async def test_image_message_skips_word_filter(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    # Image content containing blocked word in URL should NOT be filtered
    msg = await send_message(session, room_id=room.id, sender_id=user1.id, type="image", content="https://example.com/傻逼.jpg")
    assert msg.type.value == "image"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_chat.py::test_send_message -v
uv run pytest tests/test_chat.py::test_send_message_blocked_word -v
```

Expected: FAIL with `ImportError` (functions not yet defined)

- [ ] **Step 3: Implement messaging functions**

Add to `app/services/chat.py`, below the existing imports add:

```python
from app.services.word_filter import contains_blocked_word
```

Then append these functions:

```python
async def send_message(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    sender_id: uuid.UUID,
    type: str,
    content: str,
) -> Message:
    room = await get_room_by_id(session, room_id)
    if room is None:
        raise LookupError("Room not found")

    if room.is_readonly:
        raise ValueError("Room is read-only")

    # Check sender is a participant
    is_participant = any(p.user_id == sender_id for p in room.participants)
    if not is_participant:
        raise PermissionError("Not a participant")

    # Word filter for text messages only
    msg_type = MessageType(type)
    if msg_type == MessageType.TEXT and contains_blocked_word(content):
        raise ValueError("Message contains blocked content")

    message = Message(
        room_id=room_id,
        sender_id=sender_id,
        type=msg_type,
        content=content,
    )
    session.add(message)
    await session.flush()
    await session.refresh(message)
    return message


async def get_messages(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    before_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[Message]:
    query = (
        select(Message)
        .options(selectinload(Message.sender))
        .where(Message.room_id == room_id)
    )
    if before_id:
        # Get the created_at of the cursor message
        cursor_result = await session.execute(
            select(Message.created_at).where(Message.id == before_id)
        )
        cursor_time = cursor_result.scalar_one_or_none()
        if cursor_time:
            query = query.where(Message.created_at < cursor_time)

    query = query.order_by(Message.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_unread_count(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int:
    from sqlalchemy import func as sa_func

    # Get the user's last_read_at for this room
    result = await session.execute(
        select(ChatParticipant.last_read_at).where(
            ChatParticipant.room_id == room_id,
            ChatParticipant.user_id == user_id,
        )
    )
    last_read = result.scalar_one_or_none()

    count_query = select(sa_func.count(Message.id)).where(Message.room_id == room_id)
    if last_read is not None:
        count_query = count_query.where(Message.created_at > last_read)

    result = await session.execute(count_query)
    return result.scalar_one()


async def mark_room_read(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    from sqlalchemy import func as sa_func

    result = await session.execute(
        select(ChatParticipant).where(
            ChatParticipant.room_id == room_id,
            ChatParticipant.user_id == user_id,
        )
    )
    participant = result.scalar_one_or_none()
    if participant is None:
        raise LookupError("Not a participant")
    participant.last_read_at = sa_func.now()
    await session.flush()
```

- [ ] **Step 4: Run all chat tests**

```bash
uv run pytest tests/test_chat.py -v
```

Expected: all 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat.py tests/test_chat.py
git commit -m "feat(chat): add message sending, history, unread count, and word filtering"
```

---

### Task 6: REST API Endpoints

**Files:**
- Create: `app/routers/chat.py`
- Modify: `app/main.py`
- Add i18n keys: `app/i18n.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Add i18n keys for chat errors**

Add the following entries to the `_MESSAGES` dict in `app/i18n.py`:

```python
    "chat.room_not_found": {
        "zh-Hans": "聊天室不存在",
        "zh-Hant": "聊天室不存在",
        "en": "Chat room not found",
    },
    "chat.not_participant": {
        "zh-Hans": "你不是该聊天室的成员",
        "zh-Hant": "你不是該聊天室的成員",
        "en": "You are not a participant of this chat room",
    },
    "chat.room_readonly": {
        "zh-Hans": "该聊天室已设为只读",
        "zh-Hant": "該聊天室已設為唯讀",
        "en": "This chat room is read-only",
    },
    "chat.blocked_word": {
        "zh-Hans": "消息包含不当内容",
        "zh-Hant": "訊息包含不當內容",
        "en": "Message contains inappropriate content",
    },
```

- [ ] **Step 2: Write failing tests for REST endpoints**

Append to `tests/test_chat.py`:

```python
async def _register_and_get_token(client: AsyncClient, username: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


async def _seed_court(session: AsyncSession) -> Court:
    court = Court(
        name="Test Court",
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _setup_confirmed_booking_with_room(client: AsyncClient, session: AsyncSession):
    """Create two users, a confirmed booking, and the chat room. Returns (token1, token2, user1_id, user2_id, booking_id, room)."""
    token1, uid1 = await _register_and_get_token(client, "chat_user1")
    token2, uid2 = await _register_and_get_token(client, "chat_user2")
    court = await _seed_court(session)

    # Create booking
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    booking_id = resp.json()["id"]

    # User2 joins
    await client.post(
        f"/api/v1/bookings/{booking_id}/join",
        headers={"Authorization": f"Bearer {token2}"},
    )
    # Creator accepts user2
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )
    # Confirm booking → triggers chat room creation
    await client.post(
        f"/api/v1/bookings/{booking_id}/confirm",
        headers={"Authorization": f"Bearer {token1}"},
    )

    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    return token1, token2, uid1, uid2, booking_id, room


from app.services.chat import get_room_by_booking_id


@pytest.mark.asyncio
async def test_list_rooms_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.get("/api/v1/chat/rooms", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == str(room.id)
    assert data[0]["unread_count"] == 0


@pytest.mark.asyncio
async def test_send_message_rest_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "Hello from REST!"},
    )
    assert resp.status_code == 201
    assert resp.json()["content"] == "Hello from REST!"


@pytest.mark.asyncio
async def test_get_messages_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    # Send a message first
    await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "Test message"},
    )

    resp = await client.get(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Test message"


@pytest.mark.asyncio
async def test_mark_read_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    # Send message as user1
    await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "Hello"},
    )

    # User2 has 1 unread
    resp = await client.get("/api/v1/chat/rooms", headers={"Authorization": f"Bearer {token2}"})
    assert resp.json()[0]["unread_count"] == 1

    # Mark read
    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/read",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200

    # Unread now 0
    resp = await client.get("/api/v1/chat/rooms", headers={"Authorization": f"Bearer {token2}"})
    assert resp.json()[0]["unread_count"] == 0


@pytest.mark.asyncio
async def test_send_blocked_word_rest_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "你是傻逼"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_chat.py::test_list_rooms_api -v
```

Expected: FAIL (no `/api/v1/chat/rooms` route)

- [ ] **Step 4: Create the chat router**

Create `app/routers/chat.py`:

```python
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.chat import MessageResponse, RoomResponse, ParticipantInfo, SendMessageRequest
from app.services.chat import (
    get_messages,
    get_room_by_id,
    get_rooms_for_user,
    get_unread_count,
    mark_room_read,
    send_message,
)
from app.services.block import is_blocked

router = APIRouter()


def _last_message_to_response(msg) -> MessageResponse | None:
    if msg is None:
        return None
    return MessageResponse(
        id=msg.id,
        room_id=msg.room_id,
        sender_id=msg.sender_id,
        sender_nickname=msg.sender.nickname if msg.sender else None,
        type=msg.type.value,
        content=msg.content,
        is_deleted=msg.is_deleted,
        created_at=msg.created_at,
    )


@router.get("/rooms", response_model=list[RoomResponse])
async def list_rooms(user: CurrentUser, session: DbSession):
    rooms = await get_rooms_for_user(session, user.id)
    result = []
    for room in rooms:
        # Block filtering: skip private rooms where other user is blocked
        if room.type.value == "private":
            other_ids = [p.user_id for p in room.participants if p.user_id != user.id]
            if other_ids and await is_blocked(session, user.id, other_ids[0]):
                continue

        # Get last message
        messages = await get_messages(session, room_id=room.id, limit=1)
        last_msg = messages[0] if messages else None

        unread = await get_unread_count(session, room_id=room.id, user_id=user.id)

        participants = [
            ParticipantInfo(
                user_id=p.user_id,
                nickname=p.user.nickname,
                avatar_url=p.user.avatar_url,
            )
            for p in room.participants
        ]

        result.append(RoomResponse(
            id=room.id,
            type=room.type.value,
            name=room.name,
            booking_id=room.booking_id,
            is_readonly=room.is_readonly,
            participants=participants,
            last_message=_last_message_to_response(last_msg),
            unread_count=unread,
            created_at=room.created_at,
        ))
    return result


@router.get("/rooms/{room_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    room_id: str,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
    before: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    room = await get_room_by_id(session, uuid.UUID(room_id))
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("chat.room_not_found", lang))

    is_participant = any(p.user_id == user.id for p in room.participants)
    if not is_participant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("chat.not_participant", lang))

    before_id = uuid.UUID(before) if before else None
    messages = await get_messages(session, room_id=room.id, before_id=before_id, limit=limit)

    return [
        MessageResponse(
            id=m.id,
            room_id=m.room_id,
            sender_id=m.sender_id,
            sender_nickname=m.sender.nickname if m.sender else None,
            type=m.type.value,
            content=m.content,
            is_deleted=m.is_deleted,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/rooms/{room_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    room_id: str,
    body: SendMessageRequest,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
):
    try:
        msg = await send_message(
            session,
            room_id=uuid.UUID(room_id),
            sender_id=user.id,
            type=body.type,
            content=body.content,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("chat.room_not_found", lang))
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("chat.not_participant", lang))
    except ValueError as e:
        if "read-only" in str(e):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("chat.room_readonly", lang))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("chat.blocked_word", lang))

    await session.commit()
    return MessageResponse(
        id=msg.id,
        room_id=msg.room_id,
        sender_id=msg.sender_id,
        sender_nickname=user.nickname,
        type=msg.type.value,
        content=msg.content,
        is_deleted=msg.is_deleted,
        created_at=msg.created_at,
    )


@router.post("/rooms/{room_id}/read")
async def mark_read(
    room_id: str,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
):
    try:
        await mark_room_read(session, room_id=uuid.UUID(room_id), user_id=user.id)
        await session.commit()
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("chat.not_participant", lang))
    return {"status": "ok"}
```

- [ ] **Step 5: Register chat router in main.py**

In `app/main.py`, add the import:

```python
from app.routers import auth, assistant, blocks, bookings, chat, courts, follows, matching, notifications, reports, reviews, users, weather
```

And add the router registration:

```python
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
```

- [ ] **Step 6: Run REST API tests**

```bash
uv run pytest tests/test_chat.py::test_list_rooms_api tests/test_chat.py::test_send_message_rest_api tests/test_chat.py::test_get_messages_api tests/test_chat.py::test_mark_read_api tests/test_chat.py::test_send_blocked_word_rest_api -v
```

Expected: all 5 REST API tests PASS. Note: `test_list_rooms_api` and `test_setup_confirmed_booking_with_room` depend on Task 7 (booking integration) to auto-create the room on confirm. If those fail because the room isn't auto-created yet, that's expected — they'll pass after Task 7.

- [ ] **Step 7: Commit**

```bash
git add app/routers/chat.py app/main.py app/i18n.py
git commit -m "feat(chat): add REST API endpoints for rooms, messages, and mark-read"
```

---

### Task 7: Booking Integration — Auto-Create Rooms

**Files:**
- Modify: `app/services/booking.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_chat.py`:

```python
@pytest.mark.asyncio
async def test_confirm_booking_creates_chat_room(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "int_user1")
    token2, uid2 = await _register_and_get_token(client, "int_user2")
    court = await _seed_court(session)

    # Create booking
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    booking_id = resp.json()["id"]

    # User2 joins and gets accepted
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # No room yet
    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    assert room is None

    # Confirm → room should be created
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200

    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    assert room is not None
    assert room.type == RoomType.PRIVATE
    assert len(room.participants) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_chat.py::test_confirm_booking_creates_chat_room -v
```

Expected: FAIL — room is None after confirm (no integration yet)

- [ ] **Step 3: Integrate into confirm_booking()**

In `app/services/booking.py`, add the import at the top:

```python
from app.services.chat import create_chat_room
```

In the `confirm_booking()` function, after `booking.status = BookingStatus.CONFIRMED` and after the notification loop, add:

```python
    # Create chat room for confirmed booking
    accepted_ids = [p.user_id for p in booking.participants if p.status == ParticipantStatus.ACCEPTED]
    court = booking.court or await session.get(Court, booking.court_id)
    court_name = court.name if court else ""
    await create_chat_room(session, booking=booking, participant_ids=accepted_ids, court_name=court_name)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_chat.py::test_confirm_booking_creates_chat_room -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/booking.py tests/test_chat.py
git commit -m "feat(chat): auto-create chat room on booking confirmation"
```

---

### Task 8: Booking Integration — Cancel Sets Readonly + Participant Sync

**Files:**
- Modify: `app/services/booking.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_chat.py`:

```python
@pytest.mark.asyncio
async def test_cancel_booking_sets_room_readonly(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    assert room.is_readonly is False

    resp = await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200

    await session.refresh(room)
    assert room.is_readonly is True


@pytest.mark.asyncio
async def test_participant_accepted_after_room_exists(client: AsyncClient, session: AsyncSession):
    """For doubles: a late-accepted participant should be added to the chat room."""
    token1, uid1 = await _register_and_get_token(client, "dbl_user1")
    token2, uid2 = await _register_and_get_token(client, "dbl_user2")
    token3, uid3 = await _register_and_get_token(client, "dbl_user3")
    court = await _seed_court(session)

    # Create doubles booking
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "doubles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    booking_id = resp.json()["id"]

    # User2 joins and is accepted
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Confirm with 2 players
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})

    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    assert len(room.participants) == 2

    # User3 joins and is accepted after room exists
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token3}"})
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid3}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    assert len(room.participants) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_chat.py::test_cancel_booking_sets_room_readonly tests/test_chat.py::test_participant_accepted_after_room_exists -v
```

Expected: FAIL

- [ ] **Step 3: Integrate cancel_booking() with set_room_readonly**

In `app/services/booking.py`, add the import:

```python
from app.services.chat import create_chat_room, set_room_readonly, add_participant, remove_participant, get_room_by_booking_id
```

(Replace the existing `from app.services.chat import create_chat_room` if it was added in Task 7.)

In `cancel_booking()`, after `booking.status = BookingStatus.CANCELLED` (inside the `if user.id == booking.creator_id:` block), add:

```python
        await set_room_readonly(session, booking_id=booking.id)
```

- [ ] **Step 4: Integrate update_participant_status() with chat participant sync**

In `update_participant_status()`, after the status is set and before `await session.commit()`, add:

```python
            # Sync chat room participant
            if new_status == "accepted":
                room = await get_room_by_booking_id(session, booking.id)
                if room:
                    await add_participant(session, room_id=room.id, user_id=user_id)
            elif new_status == "rejected":
                room = await get_room_by_booking_id(session, booking.id)
                if room:
                    await remove_participant(session, room_id=room.id, user_id=user_id)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_chat.py::test_cancel_booking_sets_room_readonly tests/test_chat.py::test_participant_accepted_after_room_exists -v
```

Expected: PASS

- [ ] **Step 6: Run all tests to check for regressions**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/booking.py tests/test_chat.py
git commit -m "feat(chat): integrate cancel/participant-sync with chat rooms"
```

---

### Task 9: WebSocket Endpoint + ConnectionManager

**Files:**
- Modify: `app/services/chat.py`
- Modify: `app/routers/chat.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Add ConnectionManager to the chat service**

Add at the top of `app/services/chat.py`:

```python
from fastapi import WebSocket
```

Then add the `ConnectionManager` class and module-level instance:

```python
class ConnectionManager:
    def __init__(self):
        self.connections: dict[uuid.UUID, WebSocket] = {}

    async def connect(self, user_id: uuid.UUID, ws: WebSocket) -> None:
        # Replace existing connection if any
        if user_id in self.connections:
            try:
                await self.connections[user_id].close()
            except Exception:
                pass
        self.connections[user_id] = ws

    async def disconnect(self, user_id: uuid.UUID) -> None:
        self.connections.pop(user_id, None)

    async def broadcast_to_room(
        self,
        participant_ids: list[uuid.UUID],
        message: dict,
        exclude: uuid.UUID | None = None,
    ) -> None:
        for uid in participant_ids:
            if uid == exclude:
                continue
            ws = self.connections.get(uid)
            if ws:
                try:
                    await ws.send_json(message)
                except Exception:
                    self.connections.pop(uid, None)


manager = ConnectionManager()
```

- [ ] **Step 2: Add WebSocket endpoint to the router**

Add imports to `app/routers/chat.py`:

```python
import asyncio
import json
from fastapi import WebSocket, WebSocketDisconnect
from app.services.auth import decode_token
from app.services.user import get_user_by_id
from app.services.chat import manager, get_rooms_for_user as get_user_rooms
from app.database import async_session
```

Add the WebSocket endpoint:

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=4001)
        return

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=4001)
        return

    user_id_str = payload.get("sub")
    if not user_id_str:
        await websocket.close(code=4001)
        return

    user_id = uuid.UUID(user_id_str)

    await websocket.accept()
    await manager.connect(user_id, websocket)

    # Load user's room IDs for validation
    async with async_session() as session:
        user = await get_user_by_id(session, user_id)
        if not user or not user.is_active or user.is_suspended:
            await websocket.close(code=4003)
            return

    last_ping = asyncio.get_event_loop().time()

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # No message for 60s — close
                await websocket.close(code=4002)
                break

            if raw == "ping":
                await websocket.send_text("pong")
                last_ping = asyncio.get_event_loop().time()
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "data": {"code": "invalid_json", "message": "Invalid JSON"}})
                continue

            action = data.get("action")
            if action == "send":
                room_id_str = data.get("room_id")
                msg_type = data.get("type", "text")
                content = data.get("content", "")

                if not room_id_str or not content:
                    await websocket.send_json({"event": "error", "data": {"code": "missing_fields", "message": "room_id and content required"}})
                    continue

                async with async_session() as session:
                    try:
                        msg = await send_message(
                            session,
                            room_id=uuid.UUID(room_id_str),
                            sender_id=user_id,
                            type=msg_type,
                            content=content,
                        )
                        await session.commit()

                        # Get participant IDs for broadcast
                        room = await get_room_by_id(session, msg.room_id)
                        participant_ids = [p.user_id for p in room.participants]

                        msg_payload = {
                            "event": "new_message",
                            "data": {
                                "id": str(msg.id),
                                "room_id": str(msg.room_id),
                                "sender_id": str(msg.sender_id),
                                "sender_nickname": user.nickname,
                                "type": msg.type.value,
                                "content": msg.content,
                                "created_at": msg.created_at.isoformat(),
                            },
                        }

                        # Broadcast to others
                        await manager.broadcast_to_room(participant_ids, msg_payload, exclude=user_id)

                        # Ack to sender
                        await websocket.send_json({
                            "event": "ack",
                            "data": {"id": str(msg.id), "created_at": msg.created_at.isoformat()},
                        })

                    except ValueError as e:
                        error_code = "room_readonly" if "read-only" in str(e) else "blocked_word"
                        await websocket.send_json({"event": "error", "data": {"code": error_code, "message": str(e)}})
                    except PermissionError:
                        await websocket.send_json({"event": "error", "data": {"code": "not_participant", "message": "Not a participant"}})
                    except LookupError:
                        await websocket.send_json({"event": "error", "data": {"code": "room_not_found", "message": "Room not found"}})
            else:
                await websocket.send_json({"event": "error", "data": {"code": "unknown_action", "message": f"Unknown action: {action}"}})

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id)
```

- [ ] **Step 3: Write WebSocket tests**

Append to `tests/test_chat.py`:

```python
from app.services.auth import create_access_token


@pytest.mark.asyncio
async def test_websocket_send_and_receive(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    app = client._transport.app  # noqa: access underlying ASGI app

    from httpx import ASGITransport
    from starlette.testclient import TestClient
    import starlette.testclient

    # Use Starlette's TestClient for WebSocket testing
    with TestClient(app) as sync_client:
        with sync_client.websocket_connect(f"/api/v1/chat/ws?token={token1}") as ws1:
            # Send ping
            ws1.send_text("ping")
            resp = ws1.receive_text()
            assert resp == "pong"

            # Send a message
            ws1.send_json({
                "action": "send",
                "room_id": str(room.id),
                "type": "text",
                "content": "Hello via WS!",
            })
            ack = ws1.receive_json()
            assert ack["event"] == "ack"
            assert "id" in ack["data"]


@pytest.mark.asyncio
async def test_websocket_invalid_token(client: AsyncClient, session: AsyncSession):
    app = client._transport.app

    from starlette.testclient import TestClient

    with TestClient(app) as sync_client:
        with pytest.raises(Exception):
            with sync_client.websocket_connect("/api/v1/chat/ws?token=invalid_token"):
                pass
```

- [ ] **Step 4: Run WebSocket tests**

```bash
uv run pytest tests/test_chat.py::test_websocket_send_and_receive tests/test_chat.py::test_websocket_invalid_token -v
```

Expected: PASS

- [ ] **Step 5: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/chat.py app/routers/chat.py tests/test_chat.py
git commit -m "feat(chat): add WebSocket endpoint with ConnectionManager"
```

---

### Task 10: Admin Message Deletion Endpoint

**Files:**
- Modify: `app/routers/chat.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_chat.py`:

```python
from app.models.user import UserRole


@pytest.mark.asyncio
async def test_admin_delete_message(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    # Send a message
    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "delete me"},
    )
    msg_id = resp.json()["id"]

    # Make user1 an admin
    from app.models.user import User
    user = await session.get(User, uuid.UUID(uid1))
    user.role = UserRole.ADMIN
    await session.commit()

    # Delete message
    resp = await client.delete(
        f"/api/v1/admin/chat/messages/{msg_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200

    # Verify message is soft-deleted
    resp = await client.get(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.json()[0]["is_deleted"] is True


@pytest.mark.asyncio
async def test_non_admin_cannot_delete_message(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "keep me"},
    )
    msg_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/admin/chat/messages/{msg_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_chat.py::test_admin_delete_message -v
```

Expected: FAIL (404 — endpoint doesn't exist)

- [ ] **Step 3: Add admin router and delete endpoint**

In `app/routers/chat.py`, add the import:

```python
from app.dependencies import AdminUser
```

Create the admin router and add the delete endpoint:

```python
admin_router = APIRouter()


@admin_router.delete("/messages/{message_id}")
async def admin_delete_message(
    message_id: str,
    admin: AdminUser,
    session: DbSession,
    lang: Lang,
):
    from app.models.chat import Message
    msg = await session.get(Message, uuid.UUID(message_id))
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("chat.room_not_found", lang))
    msg.is_deleted = True
    await session.commit()
    return {"status": "ok"}
```

- [ ] **Step 4: Register admin router in main.py**

In `app/main.py`, add:

```python
    app.include_router(chat.admin_router, prefix="/api/v1/admin/chat", tags=["admin"])
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_chat.py::test_admin_delete_message tests/test_chat.py::test_non_admin_cannot_delete_message -v
```

Expected: PASS

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/routers/chat.py app/main.py tests/test_chat.py
git commit -m "feat(chat): add admin message soft-delete endpoint"
```

---

### Task 11: Block Integration — Private Room Readonly on Block

**Files:**
- Modify: `app/services/block.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_chat.py`:

```python
@pytest.mark.asyncio
async def test_block_sets_private_room_readonly(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    assert room.is_readonly is False

    # User1 blocks User2
    resp = await client.post(
        "/api/v1/blocks",
        headers={"Authorization": f"Bearer {token1}"},
        json={"blocked_id": uid2},
    )
    assert resp.status_code == 201

    await session.refresh(room)
    assert room.is_readonly is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_chat.py::test_block_sets_private_room_readonly -v
```

Expected: FAIL (room.is_readonly is still False)

- [ ] **Step 3: Integrate block with chat rooms**

In `app/services/block.py`, add the import:

```python
from app.models.chat import ChatParticipant, ChatRoom, RoomType
```

After the line `review.is_hidden = True` (end of the review-hiding loop) and before `await session.commit()`, add:

```python
    # Set shared private chat rooms to read-only
    from sqlalchemy import and_
    blocker_rooms = select(ChatParticipant.room_id).where(ChatParticipant.user_id == blocker_id).scalar_subquery()
    result = await session.execute(
        select(ChatRoom).where(
            ChatRoom.id.in_(
                select(ChatParticipant.room_id).where(
                    ChatParticipant.user_id == blocked_id,
                    ChatParticipant.room_id.in_(blocker_rooms),
                )
            ),
            ChatRoom.type == RoomType.PRIVATE,
            ChatRoom.is_readonly == False,  # noqa: E712
        )
    )
    for chat_room in result.scalars().all():
        chat_room.is_readonly = True
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/test_chat.py::test_block_sets_private_room_readonly -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/block.py tests/test_chat.py
git commit -m "feat(chat): set private chat rooms readonly on block"
```

---

### Task 12: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the modules table in CLAUDE.md**

Add a row for Chat in the modules table:

```
| Chat | `chat.py` | WebSocket + REST. Auto-created rooms on booking confirm. `ConnectionManager` for WS. |
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with chat system module"
```
