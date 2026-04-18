# Event System (社区赛事) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a community tournament system supporting elimination (singles/doubles) and round-robin formats with seeded draws, structured score entry, dual-confirmation, and chat integration.

**Architecture:** Follows existing monolith pattern — models/services/routers/schemas in the FastAPI app. Four new tables (Event, EventParticipant, EventMatch, EventSet). Service layer handles lifecycle, draw generation, score validation. Integrates with existing credit, notification, chat, and block systems.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Pydantic v2, Alembic

---

### Task 1: Event Models + Enums

**Files:**

- Create: `app/models/event.py`

- [ ] **Step 1: Create event models file**

Create `app/models/event.py`:

```python
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


class ParticipantStatus(str, enum.Enum):
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
    status: Mapped[ParticipantStatus] = mapped_column(Enum(ParticipantStatus), default=ParticipantStatus.REGISTERED)
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
```

- [ ] **Step 2: Verify file was created correctly**

Run: `python -c "from app.models.event import Event, EventParticipant, EventMatch, EventSet, EventType, EventStatus; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/models/event.py
git commit -m "feat(event): add Event, EventParticipant, EventMatch, EventSet models"
```

---

### Task 2: Modify Existing Models (Notification + Chat)

**Files:**

- Modify: `app/models/notification.py`
- Modify: `app/models/chat.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Add event notification types**

In `app/models/notification.py`, add these values to `NotificationType` enum (after `NEW_CHAT_MESSAGE`):

```python
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
```

- [ ] **Step 2: Add event_id to ChatRoom**

In `app/models/chat.py`, add after the `booking_id` column in `ChatRoom`:

```python
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), unique=True, nullable=True
    )
```

- [ ] **Step 3: Update models **init**.py**

In `app/models/__init__.py`, add the import and **all** entries:

```python
from app.models.event import Event, EventParticipant, EventMatch, EventSet
```

Add to `__all__`:

```python
    "Event", "EventParticipant", "EventMatch", "EventSet",
```

- [ ] **Step 4: Verify imports**

Run: `python -c "from app.models import Event, EventParticipant, EventMatch, EventSet; print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/models/notification.py app/models/chat.py app/models/__init__.py
git commit -m "feat(event): add notification types, ChatRoom.event_id, model exports"
```

---

### Task 3: Alembic Migration

**Files:**

- Create: Alembic migration file (auto-generated)

- [ ] **Step 1: Generate migration**

```bash
uv run alembic revision --autogenerate -m "add event system tables"
```

- [ ] **Step 2: Review the generated migration**

Open the generated file and verify it creates:

- `events` table
- `event_participants` table with unique constraint
- `event_matches` table
- `event_sets` table with unique constraint
- `event_id` column on `chat_rooms`
- New notification enum values

- [ ] **Step 3: Run migration**

```bash
uv run alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat(event): add event system migration"
```

---

### Task 4: i18n Messages

**Files:**

- Modify: `app/i18n.py`

- [ ] **Step 1: Add event i18n messages**

Add these entries to `_MESSAGES` dict in `app/i18n.py`:

```python
    "event.not_found": {
        "zh-Hans": "赛事未找到",
        "zh-Hant": "賽事未找到",
        "en": "Event not found",
    },
    "event.not_creator": {
        "zh-Hans": "只有组织者才能执行此操作",
        "zh-Hant": "只有組織者才能執行此操作",
        "en": "Only the event organizer can perform this action",
    },
    "event.credit_too_low": {
        "zh-Hans": "信誉积分不足，无法创建赛事",
        "zh-Hant": "信誉积分不足，無法創建賽事",
        "en": "Credit score too low to create an event",
    },
    "event.not_open": {
        "zh-Hans": "赛事不在开放报名状态",
        "zh-Hant": "賽事不在開放報名狀態",
        "en": "Event is not open for registration",
    },
    "event.already_joined": {
        "zh-Hans": "你已经报名了这个赛事",
        "zh-Hant": "你已經報名了這個賽事",
        "en": "You have already joined this event",
    },
    "event.full": {
        "zh-Hans": "赛事报名人数已满",
        "zh-Hant": "賽事報名人數已滿",
        "en": "Event registration is full",
    },
    "event.ntrp_out_of_range": {
        "zh-Hans": "你的水平不在赛事要求范围内",
        "zh-Hant": "你的水平不在賽事要求範圍內",
        "en": "Your NTRP level is outside the event's required range",
    },
    "event.gender_mismatch": {
        "zh-Hans": "该赛事有性别要求",
        "zh-Hant": "該賽事有性別要求",
        "en": "This event has a gender requirement you don't meet",
    },
    "event.not_enough_participants": {
        "zh-Hans": "参赛人数不足，无法开始",
        "zh-Hant": "參賽人數不足，無法開始",
        "en": "Not enough participants to start the event",
    },
    "event.already_started": {
        "zh-Hans": "赛事已经开始",
        "zh-Hant": "賽事已經開始",
        "en": "Event has already started",
    },
    "event.not_in_progress": {
        "zh-Hans": "赛事不在进行中",
        "zh-Hant": "賽事不在進行中",
        "en": "Event is not in progress",
    },
    "event.cannot_modify": {
        "zh-Hans": "赛事当前状态不允许修改",
        "zh-Hant": "賽事當前狀態不允許修改",
        "en": "Event cannot be modified in its current status",
    },
    "event.match_not_found": {
        "zh-Hans": "比赛未找到",
        "zh-Hant": "比賽未找到",
        "en": "Match not found",
    },
    "event.not_match_player": {
        "zh-Hans": "你不是这场比赛的选手",
        "zh-Hant": "你不是這場比賽的選手",
        "en": "You are not a player in this match",
    },
    "event.match_not_ready": {
        "zh-Hans": "比赛尚未就绪（等待对手）",
        "zh-Hant": "比賽尚未就緒（等待對手）",
        "en": "Match is not ready (waiting for opponent)",
    },
    "event.score_already_submitted": {
        "zh-Hans": "比分已提交，等待确认",
        "zh-Hant": "比分已提交，等待確認",
        "en": "Score already submitted, awaiting confirmation",
    },
    "event.score_invalid": {
        "zh-Hans": "比分不合法",
        "zh-Hant": "比分不合法",
        "en": "Invalid score",
    },
    "event.match_not_submitted": {
        "zh-Hans": "比赛尚未提交比分",
        "zh-Hant": "比賽尚未提交比分",
        "en": "No score has been submitted for this match",
    },
    "event.cannot_confirm_own": {
        "zh-Hans": "不能确认自己提交的比分",
        "zh-Hant": "不能確認自己提交的比分",
        "en": "Cannot confirm your own score submission",
    },
    "event.not_registered": {
        "zh-Hans": "你未报名此赛事",
        "zh-Hant": "你未報名此賽事",
        "en": "You are not registered for this event",
    },
    "event.cannot_withdraw": {
        "zh-Hans": "赛事已开始，无法退出",
        "zh-Hant": "賽事已開始，無法退出",
        "en": "Cannot withdraw after the event has started",
    },
    "event.walkover_already_decided": {
        "zh-Hans": "该比赛已有结果",
        "zh-Hant": "該比賽已有結果",
        "en": "This match already has a result",
    },
```

- [ ] **Step 2: Verify i18n loads**

Run: `python -c "from app.i18n import t; print(t('event.not_found', 'en'))"`

Expected: `Event not found`

- [ ] **Step 3: Commit**

```bash
git add app/i18n.py
git commit -m "feat(event): add i18n messages for event system"
```

---

### Task 5: Event Schemas

**Files:**

- Create: `app/schemas/event.py`

- [ ] **Step 1: Create event schemas**

Create `app/schemas/event.py`:

```python
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class EventCreateRequest(BaseModel):
    name: str = Field(..., max_length=100)
    event_type: str = Field(..., pattern=r"^(singles_elimination|doubles_elimination|round_robin)$")
    min_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    max_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    gender_requirement: str = Field(default="any", pattern=r"^(male_only|female_only|any)$")
    max_participants: int = Field(..., ge=3, le=64)
    games_per_set: int = Field(default=6, ge=4, le=6)
    num_sets: int = Field(default=3, ge=1, le=3)
    match_tiebreak: bool = Field(default=False)
    start_date: date | None = None
    end_date: date | None = None
    registration_deadline: datetime
    entry_fee: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=1000)


class EventUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    max_participants: int | None = Field(default=None, ge=3, le=64)
    games_per_set: int | None = Field(default=None, ge=4, le=6)
    num_sets: int | None = Field(default=None, ge=1, le=3)
    match_tiebreak: bool | None = None
    start_date: date | None = None
    end_date: date | None = None
    registration_deadline: datetime | None = None
    entry_fee: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=1000)


class EventParticipantResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    nickname: str
    ntrp_level: str
    seed: int | None
    group_name: str | None
    team_name: str | None
    status: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    id: uuid.UUID
    creator_id: uuid.UUID
    name: str
    event_type: str
    min_ntrp: str
    max_ntrp: str
    gender_requirement: str
    max_participants: int
    games_per_set: int
    num_sets: int
    match_tiebreak: bool
    start_date: date | None
    end_date: date | None
    registration_deadline: datetime
    entry_fee: int | None
    description: str | None
    status: str
    participant_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EventDetailResponse(EventResponse):
    participants: list[EventParticipantResponse]


class EventSetResponse(BaseModel):
    set_number: int
    score_a: int
    score_b: int
    tiebreak_a: int | None
    tiebreak_b: int | None

    model_config = {"from_attributes": True}


class EventMatchResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    round: int
    match_order: int
    player_a_id: uuid.UUID | None
    player_b_id: uuid.UUID | None
    winner_id: uuid.UUID | None
    group_name: str | None
    status: str
    submitted_by: uuid.UUID | None
    confirmed_at: datetime | None
    sets: list[EventSetResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class ScoreSubmitRequest(BaseModel):
    sets: list["SetScoreInput"]


class SetScoreInput(BaseModel):
    set_number: int = Field(..., ge=1, le=3)
    score_a: int = Field(..., ge=0)
    score_b: int = Field(..., ge=0)
    tiebreak_a: int | None = None
    tiebreak_b: int | None = None


class StandingsEntry(BaseModel):
    user_id: uuid.UUID
    nickname: str
    group_name: str
    wins: int
    losses: int
    points: int
    sets_won: int
    sets_lost: int
```

- [ ] **Step 2: Verify schemas load**

Run: `python -c "from app.schemas.event import EventCreateRequest, EventResponse, ScoreSubmitRequest; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/event.py
git commit -m "feat(event): add request/response schemas"
```

---

### Task 6: Chat Service — Event Room Helper

**Files:**

- Modify: `app/services/chat.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_events.py` (create the file):

```python
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.event import Event, EventType, EventStatus, EventParticipant, ParticipantStatus
from app.models.user import User


async def _register_and_get_token(client: AsyncClient, username: str, gender: str = "male", ntrp: str = "3.5") -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": gender,
            "city": "Hong Kong",
            "ntrp_level": ntrp,
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


def _future_deadline() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


@pytest.mark.asyncio
async def test_create_event_chat_room(session: AsyncSession):
    """Test that create_event_chat_room creates a group chat room linked to an event."""
    from app.models.user import Gender
    from app.services.chat import create_event_chat_room

    # Create two users
    user1 = User(nickname="P1", gender=Gender.MALE, city="HK", ntrp_level="3.5", ntrp_label="3.5 中級")
    user2 = User(nickname="P2", gender=Gender.MALE, city="HK", ntrp_level="3.5", ntrp_label="3.5 中級")
    session.add_all([user1, user2])
    await session.flush()

    # Create an event
    event = Event(
        creator_id=user1.id,
        name="Test Tournament",
        event_type=EventType.SINGLES_ELIMINATION,
        min_ntrp="3.0",
        max_ntrp="4.0",
        max_participants=8,
        registration_deadline=datetime.now(timezone.utc) + timedelta(days=7),
        status=EventStatus.IN_PROGRESS,
    )
    session.add(event)
    await session.flush()

    room = await create_event_chat_room(session, event=event, participant_ids=[user1.id, user2.id])

    assert room is not None
    assert room.event_id == event.id
    assert room.name == "Test Tournament"
    assert room.type.value == "group"
    assert len(room.participants) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py::test_create_event_chat_room -v`

Expected: FAIL — `create_event_chat_room` does not exist

- [ ] **Step 3: Implement create_event_chat_room**

Add to `app/services/chat.py`, after the existing `create_chat_room` function:

```python
async def create_event_chat_room(
    session: AsyncSession,
    *,
    event: "Event",
    participant_ids: list[uuid.UUID],
) -> ChatRoom:
    room = ChatRoom(
        type=RoomType.GROUP,
        event_id=event.id,
        name=event.name,
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
```

Also add a helper to find a room by event_id, after `get_room_by_booking_id`:

```python
async def get_room_by_event_id(session: AsyncSession, event_id: uuid.UUID) -> ChatRoom | None:
    result = await session.execute(
        select(ChatRoom)
        .options(
            selectinload(ChatRoom.participants).selectinload(ChatParticipant.user),
        )
        .where(ChatRoom.event_id == event_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def set_event_room_readonly(session: AsyncSession, *, event_id: uuid.UUID) -> None:
    room = await get_room_by_event_id(session, event_id)
    if room:
        room.is_readonly = True
        await session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py::test_create_event_chat_room -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat.py tests/test_events.py
git commit -m "feat(event): add create_event_chat_room and helpers"
```

---

### Task 7: Event Service — Create, Get, List

**Files:**

- Create: `app/services/event.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_create_event(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "organizer1")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Spring Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "games_per_set": 6,
            "num_sets": 3,
            "match_tiebreak": False,
            "registration_deadline": _future_deadline(),
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Spring Cup"
    assert data["status"] == "draft"
    assert data["event_type"] == "singles_elimination"
    assert data["participant_count"] == 0


@pytest.mark.asyncio
async def test_create_event_credit_too_low(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "lowcred_org")

    from sqlalchemy import update
    await session.execute(update(User).where(User.id == uuid.UUID(user_id)).values(credit_score=70))
    await session.commit()

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Bad Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_event_detail(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "detail_org")

    create_resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Detail Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Cup"
    assert data["participants"] == []


@pytest.mark.asyncio
async def test_list_events(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "list_org")

    # Create and publish an event
    create_resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "List Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = create_resp.json()["id"]

    # Publish it so it shows in listings
    await client.post(
        f"/api/v1/events/{event_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(e["name"] == "List Cup" for e in data)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_events.py::test_create_event tests/test_events.py::test_create_event_credit_too_low tests/test_events.py::test_get_event_detail tests/test_events.py::test_list_events -v`

Expected: FAIL — no router, no service

- [ ] **Step 3: Create event service with create, get, list**

Create `app/services/event.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.block import Block
from app.models.event import (
    Event,
    EventMatch,
    EventMatchStatus,
    EventParticipant,
    EventSet,
    EventStatus,
    EventType,
    ParticipantStatus,
)
from app.models.notification import NotificationType
from app.models.user import Gender, User
from app.services.notification import create_notification


def _ntrp_to_float(level: str) -> float:
    base = level.rstrip("+-")
    value = float(base)
    if level.endswith("+"):
        value += 0.05
    elif level.endswith("-"):
        value -= 0.05
    return value


async def create_event(
    session: AsyncSession,
    *,
    creator: User,
    name: str,
    event_type: str,
    min_ntrp: str,
    max_ntrp: str,
    gender_requirement: str = "any",
    max_participants: int,
    games_per_set: int = 6,
    num_sets: int = 3,
    match_tiebreak: bool = False,
    start_date=None,
    end_date=None,
    registration_deadline: datetime,
    entry_fee: int | None = None,
    description: str | None = None,
) -> Event:
    event = Event(
        creator_id=creator.id,
        name=name,
        event_type=EventType(event_type),
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_requirement=gender_requirement,
        max_participants=max_participants,
        games_per_set=games_per_set,
        num_sets=num_sets,
        match_tiebreak=match_tiebreak,
        start_date=start_date,
        end_date=end_date,
        registration_deadline=registration_deadline,
        entry_fee=entry_fee,
        description=description,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def get_event_by_id(session: AsyncSession, event_id: uuid.UUID) -> Event | None:
    result = await session.execute(
        select(Event)
        .options(
            selectinload(Event.participants).selectinload(EventParticipant.user),
            selectinload(Event.creator),
        )
        .where(Event.id == event_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def list_events(
    session: AsyncSession,
    *,
    status: str | None = None,
    event_type: str | None = None,
    current_user_id: uuid.UUID | None = None,
) -> list[Event]:
    query = select(Event).join(User, Event.creator_id == User.id)

    if status:
        query = query.where(Event.status == EventStatus(status))
    else:
        # By default show open and in_progress events
        query = query.where(Event.status.in_([EventStatus.OPEN, EventStatus.IN_PROGRESS]))

    if event_type:
        query = query.where(Event.event_type == EventType(event_type))

    if current_user_id:
        blocked_ids = select(Block.blocked_id).where(Block.blocker_id == current_user_id)
        blocker_ids = select(Block.blocker_id).where(Block.blocked_id == current_user_id)
        query = query.where(
            Event.creator_id.notin_(blocked_ids),
            Event.creator_id.notin_(blocker_ids),
        )

    query = query.order_by(User.is_ideal_player.desc(), Event.registration_deadline)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_my_events(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[Event]:
    # Events I created or joined
    created = select(Event.id).where(Event.creator_id == user_id)
    joined = select(EventParticipant.event_id).where(EventParticipant.user_id == user_id)
    query = (
        select(Event)
        .where(Event.id.in_(created.union(joined)))
        .order_by(Event.created_at.desc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_event(
    session: AsyncSession,
    event: Event,
    **kwargs,
) -> Event:
    for key, value in kwargs.items():
        if value is not None:
            setattr(event, key, value)
    await session.commit()
    await session.refresh(event)
    return event
```

- [ ] **Step 4: Create the router with CRUD endpoints**

Create `app/routers/events.py`:

```python
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.models.event import EventStatus, ParticipantStatus
from app.schemas.event import (
    EventCreateRequest,
    EventDetailResponse,
    EventMatchResponse,
    EventParticipantResponse,
    EventResponse,
    EventUpdateRequest,
    ScoreSubmitRequest,
    StandingsEntry,
)
from app.services.event import (
    create_event,
    get_event_by_id,
    list_events,
    list_my_events,
    update_event,
)

router = APIRouter()


def _participant_response(p) -> EventParticipantResponse:
    return EventParticipantResponse(
        id=p.id,
        user_id=p.user_id,
        nickname=p.user.nickname,
        ntrp_level=p.user.ntrp_level,
        seed=p.seed,
        group_name=p.group_name,
        team_name=p.team_name,
        status=p.status.value,
        joined_at=p.joined_at,
    )


def _event_to_response(event, include_participants: bool = False) -> dict:
    participant_count = len(event.participants) if event.participants else 0
    data = EventResponse(
        id=event.id,
        creator_id=event.creator_id,
        name=event.name,
        event_type=event.event_type.value,
        min_ntrp=event.min_ntrp,
        max_ntrp=event.max_ntrp,
        gender_requirement=event.gender_requirement,
        max_participants=event.max_participants,
        games_per_set=event.games_per_set,
        num_sets=event.num_sets,
        match_tiebreak=event.match_tiebreak,
        start_date=event.start_date,
        end_date=event.end_date,
        registration_deadline=event.registration_deadline,
        entry_fee=event.entry_fee,
        description=event.description,
        status=event.status.value,
        participant_count=participant_count,
        created_at=event.created_at,
    )
    if include_participants:
        participants = [_participant_response(p) for p in event.participants]
        return EventDetailResponse(**data.model_dump(), participants=participants)
    return data


@router.post("", response_model=EventDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_new_event(body: EventCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    if user.credit_score < 80:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("event.credit_too_low", lang))

    event = await create_event(
        session,
        creator=user,
        name=body.name,
        event_type=body.event_type,
        min_ntrp=body.min_ntrp,
        max_ntrp=body.max_ntrp,
        gender_requirement=body.gender_requirement,
        max_participants=body.max_participants,
        games_per_set=body.games_per_set,
        num_sets=body.num_sets,
        match_tiebreak=body.match_tiebreak,
        start_date=body.start_date,
        end_date=body.end_date,
        registration_deadline=body.registration_deadline,
        entry_fee=body.entry_fee,
        description=body.description,
    )
    event = await get_event_by_id(session, event.id)
    return _event_to_response(event, include_participants=True)


@router.get("", response_model=list[EventResponse])
async def get_events(
    session: DbSession,
    user: CurrentUser,
    event_status: str | None = Query(default=None, alias="status", pattern=r"^(draft|open|in_progress|completed|cancelled)$"),
    event_type: str | None = Query(default=None, pattern=r"^(singles_elimination|doubles_elimination|round_robin)$"),
):
    events = await list_events(session, status=event_status, event_type=event_type, current_user_id=user.id)
    return [_event_to_response(e) for e in events]


@router.get("/my", response_model=list[EventResponse])
async def get_my_events(user: CurrentUser, session: DbSession):
    events = await list_my_events(session, user.id)
    return [_event_to_response(e) for e in events]


@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(event_id: str, session: DbSession, user: CurrentUser, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    return _event_to_response(event, include_participants=True)


@router.patch("/{event_id}", response_model=EventDetailResponse)
async def update_existing_event(event_id: str, body: EventUpdateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    if event.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("event.not_creator", lang))
    if event.status not in (EventStatus.DRAFT, EventStatus.OPEN):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("event.cannot_modify", lang))

    updates = body.model_dump(exclude_unset=True)
    event = await update_event(session, event, **updates)
    event = await get_event_by_id(session, event.id)
    return _event_to_response(event, include_participants=True)
```

- [ ] **Step 5: Register the router in main.py**

In `app/main.py`, add to the imports:

```python
    from app.routers import auth, assistant, blocks, bookings, chat, courts, events, follows, matching, notifications, reports, reviews, users, weather
```

Add after the weather router:

```python
    app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_events.py::test_create_event tests/test_events.py::test_create_event_credit_too_low tests/test_events.py::test_get_event_detail tests/test_events.py::test_list_events -v`

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/event.py app/routers/events.py app/main.py tests/test_events.py
git commit -m "feat(event): add event CRUD service, router, and tests"
```

---

### Task 8: Publish + Registration (Join/Withdraw/Remove)

**Files:**

- Modify: `app/services/event.py`
- Modify: `app/routers/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_publish_event(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "pub_org")
    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Pub Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/events/{event_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"


@pytest.mark.asyncio
async def test_join_event(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "join_org", ntrp="3.5")
    player_token, _ = await _register_and_get_token(client, "join_player", ntrp="3.5")

    # Create and publish
    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Join Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Join
    resp = await client.post(
        f"/api/v1/events/{event_id}/join",
        headers={"Authorization": f"Bearer {player_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["participant_count"] == 1


@pytest.mark.asyncio
async def test_join_event_ntrp_out_of_range(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "ntrp_org", ntrp="3.5")
    player_token, _ = await _register_and_get_token(client, "ntrp_player", ntrp="5.0")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "NTRP Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/join",
        headers={"Authorization": f"Bearer {player_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_withdraw_from_event(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "wd_org", ntrp="3.5")
    player_token, _ = await _register_and_get_token(client, "wd_player", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "WD Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})
    await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {player_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/withdraw",
        headers={"Authorization": f"Bearer {player_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["participant_count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_events.py::test_publish_event tests/test_events.py::test_join_event tests/test_events.py::test_join_event_ntrp_out_of_range tests/test_events.py::test_withdraw_from_event -v`

Expected: FAIL

- [ ] **Step 3: Add service functions**

Add to `app/services/event.py`:

```python
async def publish_event(session: AsyncSession, event: Event) -> Event:
    event.status = EventStatus.OPEN
    await session.commit()
    await session.refresh(event)
    return event


async def join_event(
    session: AsyncSession,
    event: Event,
    user: User,
    lang: str = "en",
) -> Event:
    from app.i18n import t
    from app.services.block import is_blocked

    if event.status != EventStatus.OPEN:
        raise ValueError(t("event.not_open", lang))

    # Check already joined
    for p in event.participants:
        if p.user_id == user.id and p.status != ParticipantStatus.WITHDRAWN:
            raise LookupError(t("event.already_joined", lang))

    # Check NTRP
    user_ntrp = _ntrp_to_float(user.ntrp_level)
    if user_ntrp < _ntrp_to_float(event.min_ntrp) or user_ntrp > _ntrp_to_float(event.max_ntrp):
        raise PermissionError(t("event.ntrp_out_of_range", lang))

    # Check gender
    if event.gender_requirement == "male_only" and user.gender != Gender.MALE:
        raise PermissionError(t("event.gender_mismatch", lang))
    if event.gender_requirement == "female_only" and user.gender != Gender.FEMALE:
        raise PermissionError(t("event.gender_mismatch", lang))

    # Check block
    if await is_blocked(session, user.id, event.creator_id):
        raise PermissionError(t("block.user_blocked", lang))

    # Check capacity
    active_count = sum(1 for p in event.participants if p.status == ParticipantStatus.REGISTERED)
    if active_count >= event.max_participants:
        raise LookupError(t("event.full", lang))

    participant = EventParticipant(
        event_id=event.id,
        user_id=user.id,
    )
    session.add(participant)

    # Notify organizer
    await create_notification(
        session,
        recipient_id=event.creator_id,
        type=NotificationType.EVENT_JOINED,
        actor_id=user.id,
        target_type="event",
        target_id=event.id,
    )

    await session.commit()
    event = await get_event_by_id(session, event.id)
    return event


async def withdraw_from_event(
    session: AsyncSession,
    event: Event,
    user: User,
    lang: str = "en",
) -> Event:
    from app.i18n import t

    if event.status not in (EventStatus.OPEN, EventStatus.DRAFT):
        raise ValueError(t("event.cannot_withdraw", lang))

    for p in event.participants:
        if p.user_id == user.id and p.status == ParticipantStatus.REGISTERED:
            p.status = ParticipantStatus.WITHDRAWN
            await session.commit()
            event = await get_event_by_id(session, event.id)
            return event

    raise ValueError(t("event.not_registered", lang))


async def remove_participant(
    session: AsyncSession,
    event: Event,
    target_user_id: uuid.UUID,
    lang: str = "en",
) -> Event:
    from app.i18n import t

    for p in event.participants:
        if p.user_id == target_user_id and p.status == ParticipantStatus.REGISTERED:
            p.status = ParticipantStatus.WITHDRAWN
            await session.commit()
            event = await get_event_by_id(session, event.id)
            return event

    raise ValueError(t("event.not_registered", lang))
```

- [ ] **Step 4: Add router endpoints**

Add to `app/routers/events.py` imports:

```python
from app.services.event import (
    create_event,
    get_event_by_id,
    join_event,
    list_events,
    list_my_events,
    publish_event,
    remove_participant,
    update_event,
    withdraw_from_event,
)
```

Add these endpoints after the PATCH endpoint:

```python
@router.post("/{event_id}/publish", response_model=EventDetailResponse)
async def publish_existing_event(event_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    if event.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("event.not_creator", lang))
    if event.status != EventStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("event.cannot_modify", lang))

    event = await publish_event(session, event)
    event = await get_event_by_id(session, event.id)
    return _event_to_response(event, include_participants=True)


@router.post("/{event_id}/join", response_model=EventDetailResponse)
async def join_existing_event(event_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))

    try:
        event = await join_event(session, event, user, lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return _event_to_response(event, include_participants=True)


@router.post("/{event_id}/withdraw", response_model=EventDetailResponse)
async def withdraw_from_existing_event(event_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))

    try:
        event = await withdraw_from_event(session, event, user, lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _event_to_response(event, include_participants=True)


@router.delete("/{event_id}/participants/{user_id}", response_model=EventDetailResponse)
async def remove_event_participant(event_id: str, user_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    if event.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("event.not_creator", lang))
    if event.status != EventStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("event.not_open", lang))

    try:
        event = await remove_participant(session, event, uuid.UUID(user_id), lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _event_to_response(event, include_participants=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_events.py::test_publish_event tests/test_events.py::test_join_event tests/test_events.py::test_join_event_ntrp_out_of_range tests/test_events.py::test_withdraw_from_event -v`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/event.py app/routers/events.py tests/test_events.py
git commit -m "feat(event): add publish, join, withdraw, remove participant"
```

---

### Task 9: Start Event + Seeding + Elimination Draw

**Files:**

- Modify: `app/services/event.py`
- Modify: `app/routers/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_start_elimination_event(client: AsyncClient, session: AsyncSession):
    """Start an elimination event with 5 players — should create bracket with BYEs."""
    org_token, _ = await _register_and_get_token(client, "elim_org", ntrp="4.0")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Elim Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Register 4 more players (5 total including org joins separately)
    tokens = []
    for i in range(5):
        ntrp = f"{3.0 + i * 0.25:.1f}"
        tk, _ = await _register_and_get_token(client, f"elim_p{i}", ntrp=ntrp)
        tokens.append(tk)
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    # Start the event
    resp = await client.post(
        f"/api/v1/events/{event_id}/start",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    # Check matches were generated
    resp = await client.get(
        f"/api/v1/events/{event_id}/matches",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    matches = resp.json()
    # 5 players → 8 bracket → 4 first-round + 2 second-round + 1 final = 7 matches
    assert len(matches) == 7
    # Some first-round matches should be BYEs (confirmed with winner)
    round1 = [m for m in matches if m["round"] == 1]
    assert len(round1) == 4
    byes = [m for m in round1 if m["player_b_id"] is None]
    assert len(byes) == 3  # 8 - 5 = 3 BYEs


@pytest.mark.asyncio
async def test_start_event_not_enough_participants(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "few_org")
    player_token, _ = await _register_and_get_token(client, "few_p1")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Few Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})
    # Only 2 players join (need ≥ 4 for elimination)
    await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {org_token}"})
    await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {player_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/start",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_events.py::test_start_elimination_event tests/test_events.py::test_start_event_not_enough_participants -v`

Expected: FAIL

- [ ] **Step 3: Add seeding and elimination draw logic**

Add to `app/services/event.py`:

```python
import math
import random

from app.services.chat import create_event_chat_room


def _seed_participants(participants: list[EventParticipant]) -> list[EventParticipant]:
    """Sort participants by NTRP desc, credit_score desc, then random. Assign seed numbers."""
    def sort_key(p):
        return (-_ntrp_to_float(p.user.ntrp_level), -p.user.credit_score, random.random())

    sorted_p = sorted(participants, key=sort_key)
    for i, p in enumerate(sorted_p):
        p.seed = i + 1
    return sorted_p


def _generate_elimination_draw(
    seeded: list[EventParticipant],
) -> list[dict]:
    """Generate elimination bracket matches. Returns list of match dicts."""
    n = len(seeded)
    bracket_size = 2 ** math.ceil(math.log2(n))
    num_byes = bracket_size - n
    total_rounds = int(math.log2(bracket_size))

    # Place seeds into bracket positions
    # Standard tennis draw: seed 1 top, seed 2 bottom, 3/4 in opposite quarters
    positions = [None] * bracket_size

    if n >= 1:
        positions[0] = seeded[0]  # Seed 1 at top
    if n >= 2:
        positions[bracket_size - 1] = seeded[1]  # Seed 2 at bottom
    if n >= 3:
        positions[bracket_size // 2] = seeded[2]  # Seed 3 bottom of top half
    if n >= 4:
        positions[bracket_size // 2 - 1] = seeded[3]  # Seed 4 top of bottom half

    # Fill remaining seeds randomly into empty positions
    remaining = seeded[4:] if n > 4 else []
    empty_indices = [i for i, p in enumerate(positions) if p is None]
    random.shuffle(empty_indices)

    for i, p in enumerate(remaining):
        positions[empty_indices[i]] = p

    # BYE positions: remaining empty slots stay None
    # High seeds get BYEs — they're already placed, their opponent slot is None

    matches = []
    # Generate round 1
    for i in range(0, bracket_size, 2):
        match_order = i // 2 + 1
        player_a = positions[i]
        player_b = positions[i + 1]

        a_id = player_a.user_id if player_a else None
        b_id = player_b.user_id if player_b else None

        # Determine if BYE
        is_bye = a_id is None or b_id is None
        winner = a_id or b_id if is_bye else None
        status = EventMatchStatus.CONFIRMED if is_bye else EventMatchStatus.PENDING

        matches.append({
            "round": 1,
            "match_order": match_order,
            "player_a_id": a_id,
            "player_b_id": b_id,
            "winner_id": winner,
            "status": status,
        })

    # Generate subsequent rounds (empty shells)
    for r in range(2, total_rounds + 1):
        matches_in_round = bracket_size // (2 ** r)
        for m in range(1, matches_in_round + 1):
            matches.append({
                "round": r,
                "match_order": m,
                "player_a_id": None,
                "player_b_id": None,
                "winner_id": None,
                "status": EventMatchStatus.PENDING,
            })

    return matches


async def start_event(
    session: AsyncSession,
    event: Event,
    lang: str = "en",
) -> Event:
    from app.i18n import t

    if event.status != EventStatus.OPEN:
        raise ValueError(t("event.cannot_modify", lang))

    active_participants = [p for p in event.participants if p.status == ParticipantStatus.REGISTERED]
    is_elimination = event.event_type in (EventType.SINGLES_ELIMINATION, EventType.DOUBLES_ELIMINATION)
    min_required = 4 if is_elimination else 3

    if len(active_participants) < min_required:
        raise ValueError(t("event.not_enough_participants", lang))

    # Seed participants
    seeded = _seed_participants(active_participants)

    if is_elimination:
        match_dicts = _generate_elimination_draw(seeded)
    else:
        match_dicts = _generate_round_robin_draw(seeded)

    # Create EventMatch records
    for md in match_dicts:
        match = EventMatch(
            event_id=event.id,
            round=md["round"],
            match_order=md["match_order"],
            player_a_id=md["player_a_id"],
            player_b_id=md["player_b_id"],
            winner_id=md.get("winner_id"),
            group_name=md.get("group_name"),
            status=md["status"],
        )
        session.add(match)

    # For elimination: advance BYE winners to round 2
    if is_elimination:
        await session.flush()
        await _advance_bye_winners(session, event)

    # Update participant statuses
    for p in active_participants:
        p.status = ParticipantStatus.CONFIRMED

    event.status = EventStatus.IN_PROGRESS
    await session.flush()

    # Create event chat room
    participant_ids = [p.user_id for p in active_participants]
    await create_event_chat_room(session, event=event, participant_ids=participant_ids)

    # Notify all participants
    for p in active_participants:
        if p.user_id != event.creator_id:
            await create_notification(
                session,
                recipient_id=p.user_id,
                type=NotificationType.EVENT_STARTED,
                actor_id=event.creator_id,
                target_type="event",
                target_id=event.id,
            )

    await session.commit()
    event = await get_event_by_id(session, event.id)
    return event


async def _advance_bye_winners(session: AsyncSession, event: Event) -> None:
    """For elimination: fill round 2 slots with BYE winners from round 1."""
    result = await session.execute(
        select(EventMatch)
        .where(EventMatch.event_id == event.id)
        .order_by(EventMatch.round, EventMatch.match_order)
    )
    all_matches = list(result.scalars().all())

    round1 = [m for m in all_matches if m.round == 1]
    round2 = [m for m in all_matches if m.round == 2]

    for i, r2_match in enumerate(round2):
        # Each round 2 match takes winners from two round 1 matches
        r1_a = round1[i * 2]
        r1_b = round1[i * 2 + 1]

        if r1_a.winner_id is not None:
            r2_match.player_a_id = r1_a.winner_id
        if r1_b.winner_id is not None:
            r2_match.player_b_id = r1_b.winner_id

    await session.flush()
```

- [ ] **Step 4: Add placeholder for round-robin draw (implemented in next task)**

Add a temporary placeholder to `app/services/event.py`:

```python
def _generate_round_robin_draw(seeded: list[EventParticipant]) -> list[dict]:
    """Generate round-robin group matches. Full implementation in Task 10."""
    raise NotImplementedError("Round-robin draw not yet implemented")
```

- [ ] **Step 5: Add router endpoints for start and matches listing**

Add to `app/routers/events.py` imports:

```python
from app.services.event import (
    create_event,
    get_event_by_id,
    get_event_matches,
    join_event,
    list_events,
    list_my_events,
    publish_event,
    remove_participant,
    start_event,
    update_event,
    withdraw_from_event,
)
```

Add endpoints:

```python
@router.post("/{event_id}/start", response_model=EventDetailResponse)
async def start_existing_event(event_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    if event.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("event.not_creator", lang))

    try:
        event = await start_event(session, event, lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _event_to_response(event, include_participants=True)


@router.get("/{event_id}/matches", response_model=list[EventMatchResponse])
async def get_matches(
    event_id: str,
    session: DbSession,
    user: CurrentUser,
    lang: Lang,
    round: int | None = Query(default=None),
    group: str | None = Query(default=None),
):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))

    matches = await get_event_matches(session, event.id, round=round, group_name=group)
    return matches
```

- [ ] **Step 6: Add get_event_matches to service**

Add to `app/services/event.py`:

```python
async def get_event_matches(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    round: int | None = None,
    group_name: str | None = None,
) -> list[EventMatch]:
    query = (
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.event_id == event_id)
    )
    if round is not None:
        query = query.where(EventMatch.round == round)
    if group_name is not None:
        query = query.where(EventMatch.group_name == group_name)
    query = query.order_by(EventMatch.round, EventMatch.match_order)
    result = await session.execute(query)
    return list(result.scalars().all())
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_events.py::test_start_elimination_event tests/test_events.py::test_start_event_not_enough_participants -v`

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add app/services/event.py app/routers/events.py tests/test_events.py
git commit -m "feat(event): add start event with seeding and elimination draw"
```

---

### Task 10: Round-Robin Draw Generation

**Files:**

- Modify: `app/services/event.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_start_round_robin_event(client: AsyncClient, session: AsyncSession):
    """Start a round-robin event with 6 players — should create groups and matches."""
    org_token, _ = await _register_and_get_token(client, "rr_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "RR Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Register 6 players
    for i in range(6):
        tk, _ = await _register_and_get_token(client, f"rr_p{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/start",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    # Check matches
    resp = await client.get(
        f"/api/v1/events/{event_id}/matches",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    matches = resp.json()

    # 6 players → 2 groups of 3 → each group has C(3,2) = 3 matches → 6 total
    assert len(matches) == 6

    # All matches should have group_name
    groups = set(m["group_name"] for m in matches)
    assert len(groups) == 2
    assert "A" in groups
    assert "B" in groups
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py::test_start_round_robin_event -v`

Expected: FAIL — NotImplementedError

- [ ] **Step 3: Implement round-robin draw**

Replace the `_generate_round_robin_draw` placeholder in `app/services/event.py`:

```python
def _generate_round_robin_draw(seeded: list[EventParticipant]) -> list[dict]:
    """Generate round-robin matches with snake-draft grouping."""
    n = len(seeded)
    # Determine group count: target 3-4 per group
    if n <= 4:
        num_groups = 1
    else:
        num_groups = max(2, n // 4)

    # Snake-draft into groups
    groups: dict[str, list[EventParticipant]] = {}
    group_labels = [chr(ord("A") + i) for i in range(num_groups)]
    for label in group_labels:
        groups[label] = []

    for i, p in enumerate(seeded):
        cycle = i // num_groups
        idx = i % num_groups
        if cycle % 2 == 1:
            idx = num_groups - 1 - idx
        label = group_labels[idx]
        groups[label].append(p)
        p.group_name = label

    matches = []
    for label, members in groups.items():
        group_matches = _round_robin_schedule(members, label)
        matches.extend(group_matches)

    return matches


def _round_robin_schedule(members: list[EventParticipant], group_name: str) -> list[dict]:
    """Generate all-play-all matches using circle method."""
    n = len(members)
    if n < 2:
        return []

    players = list(members)
    if n % 2 == 1:
        players.append(None)  # Dummy for bye

    num_rounds = len(players) - 1
    matches = []
    match_order = 1

    for round_num in range(1, num_rounds + 1):
        for i in range(len(players) // 2):
            a = players[i]
            b = players[len(players) - 1 - i]
            if a is None or b is None:
                continue  # Skip bye
            matches.append({
                "round": round_num,
                "match_order": match_order,
                "player_a_id": a.user_id,
                "player_b_id": b.user_id,
                "winner_id": None,
                "group_name": group_name,
                "status": EventMatchStatus.PENDING,
            })
            match_order += 1

        # Rotate: fix first player, rotate rest
        players = [players[0]] + [players[-1]] + players[1:-1]

    return matches
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py::test_start_round_robin_event -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/event.py tests/test_events.py
git commit -m "feat(event): add round-robin draw generation with snake grouping"
```

---

### Task 11: Score Submission + Validation

**Files:**

- Modify: `app/services/event.py`
- Modify: `app/routers/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_submit_score(client: AsyncClient, session: AsyncSession):
    """Submit a valid score for a round-robin match."""
    org_token, org_id = await _register_and_get_token(client, "sc_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Score Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"sc_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    # Get matches
    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    matches = resp.json()
    match_id = matches[0]["id"]
    submitter_id = matches[0]["player_a_id"]

    # Find the token for player_a
    submitter_token = None
    for tk, pid in player_tokens:
        if pid == submitter_id:
            submitter_token = tk
            break

    # Submit score: 6-4 6-3 (best of 3, player A wins in 2 sets)
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {submitter_token}"},
        json={
            "sets": [
                {"set_number": 1, "score_a": 6, "score_b": 4},
                {"set_number": 2, "score_a": 6, "score_b": 3},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"
    assert data["winner_id"] == submitter_id
    assert len(data["sets"]) == 2


@pytest.mark.asyncio
async def test_submit_score_invalid(client: AsyncClient, session: AsyncSession):
    """Submit an invalid score (e.g., 6-5 without tiebreak) — should fail."""
    org_token, _ = await _register_and_get_token(client, "inv_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Invalid Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"inv_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match_id = resp.json()[0]["id"]
    submitter_id = resp.json()[0]["player_a_id"]
    submitter_token = next(tk for tk, pid in player_tokens if pid == submitter_id)

    # Invalid: 6-5 without tiebreak
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {submitter_token}"},
        json={
            "sets": [
                {"set_number": 1, "score_a": 6, "score_b": 5},
            ]
        },
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_events.py::test_submit_score tests/test_events.py::test_submit_score_invalid -v`

Expected: FAIL

- [ ] **Step 3: Add score validation and submission logic**

Add to `app/services/event.py`:

```python
def validate_set_score(score_a: int, score_b: int, tiebreak_a: int | None, tiebreak_b: int | None, games_per_set: int, is_match_tiebreak: bool = False) -> bool:
    """Validate a single set score based on games_per_set configuration."""
    if is_match_tiebreak:
        # Match tiebreak: score is 1-0 or 0-1, tiebreak scores required
        if not ((score_a == 1 and score_b == 0) or (score_a == 0 and score_b == 1)):
            return False
        if tiebreak_a is None or tiebreak_b is None:
            return False
        winner_tb = max(tiebreak_a, tiebreak_b)
        loser_tb = min(tiebreak_a, tiebreak_b)
        # Must win by 2, minimum 10 points
        if winner_tb < 10:
            return False
        if winner_tb - loser_tb < 2:
            return False
        return True

    g = games_per_set
    high = max(score_a, score_b)
    low = min(score_a, score_b)

    # Normal win: winner has g games, lead by >= 2
    if high == g and low <= g - 2:
        if tiebreak_a is not None or tiebreak_b is not None:
            return False
        return True

    # Tiebreak: g+1 vs g (e.g., 7-6 for 6-game sets, 5-4 for 4-game sets)
    if high == g + 1 and low == g:
        if tiebreak_a is None or tiebreak_b is None:
            return False
        winner_tb = max(tiebreak_a, tiebreak_b)
        loser_tb = min(tiebreak_a, tiebreak_b)
        if winner_tb < 7:
            return False
        if winner_tb - loser_tb < 2:
            return False
        return True

    return False


def validate_match_score(sets: list[dict], games_per_set: int, num_sets: int, match_tiebreak: bool) -> uuid.UUID | None:
    """Validate all sets and determine winner. Returns winner ('a' or 'b') or None if invalid."""
    sets_to_win = (num_sets // 2) + 1
    a_wins = 0
    b_wins = 0

    for i, s in enumerate(sets):
        is_deciding_set = (i == num_sets - 1) and match_tiebreak and (a_wins == sets_to_win - 1) and (b_wins == sets_to_win - 1)

        if not validate_set_score(s["score_a"], s["score_b"], s.get("tiebreak_a"), s.get("tiebreak_b"), games_per_set, is_match_tiebreak=is_deciding_set):
            return None

        if is_deciding_set:
            if s["score_a"] > s["score_b"]:
                a_wins += 1
            else:
                b_wins += 1
        else:
            if s["score_a"] > s["score_b"]:
                a_wins += 1
            elif s["score_b"] > s["score_a"]:
                b_wins += 1
            else:
                return None  # Tie in a set is invalid

    # Check someone won enough sets
    if a_wins >= sets_to_win:
        return "a"
    if b_wins >= sets_to_win:
        return "b"

    # Not enough sets played — invalid unless match is already decided
    return None


async def submit_score(
    session: AsyncSession,
    match: EventMatch,
    submitter_id: uuid.UUID,
    sets_data: list[dict],
    lang: str = "en",
) -> EventMatch:
    from app.i18n import t

    if match.status not in (EventMatchStatus.PENDING,):
        raise ValueError(t("event.score_already_submitted", lang))

    if match.player_a_id is None or match.player_b_id is None:
        raise ValueError(t("event.match_not_ready", lang))

    if submitter_id not in (match.player_a_id, match.player_b_id):
        raise PermissionError(t("event.not_match_player", lang))

    # Get event for scoring config
    event = await get_event_by_id(session, match.event_id)

    # Validate scores
    winner_side = validate_match_score(
        sets_data,
        games_per_set=event.games_per_set,
        num_sets=event.num_sets,
        match_tiebreak=event.match_tiebreak,
    )
    if winner_side is None:
        raise ValueError(t("event.score_invalid", lang))

    winner_id = match.player_a_id if winner_side == "a" else match.player_b_id

    # Create EventSet records
    for s in sets_data:
        event_set = EventSet(
            match_id=match.id,
            set_number=s["set_number"],
            score_a=s["score_a"],
            score_b=s["score_b"],
            tiebreak_a=s.get("tiebreak_a"),
            tiebreak_b=s.get("tiebreak_b"),
        )
        session.add(event_set)

    match.status = EventMatchStatus.SUBMITTED
    match.submitted_by = submitter_id
    match.winner_id = winner_id

    # Notify opponent
    opponent_id = match.player_b_id if submitter_id == match.player_a_id else match.player_a_id
    await create_notification(
        session,
        recipient_id=opponent_id,
        type=NotificationType.EVENT_SCORE_SUBMITTED,
        actor_id=submitter_id,
        target_type="event_match",
        target_id=match.id,
    )

    await session.commit()

    # Re-fetch with sets loaded
    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def get_match_by_id(session: AsyncSession, match_id: uuid.UUID) -> EventMatch | None:
    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match_id)
    )
    return result.scalar_one_or_none()
```

- [ ] **Step 4: Add router endpoint for score submission**

Add to `app/routers/events.py` imports:

```python
from app.services.event import (
    create_event,
    get_event_by_id,
    get_event_matches,
    get_match_by_id,
    join_event,
    list_events,
    list_my_events,
    publish_event,
    remove_participant,
    start_event,
    submit_score,
    update_event,
    withdraw_from_event,
)
```

Add endpoint:

```python
@router.post("/matches/{match_id}/score", response_model=EventMatchResponse)
async def submit_match_score(match_id: str, body: ScoreSubmitRequest, user: CurrentUser, session: DbSession, lang: Lang):
    match = await get_match_by_id(session, uuid.UUID(match_id))
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.match_not_found", lang))

    try:
        match = await submit_score(session, match, user.id, [s.model_dump() for s in body.sets], lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return match
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_events.py::test_submit_score tests/test_events.py::test_submit_score_invalid -v`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/event.py app/routers/events.py tests/test_events.py
git commit -m "feat(event): add score submission with validation"
```

---

### Task 12: Score Confirmation + Dispute + Auto-Advance

**Files:**

- Modify: `app/services/event.py`
- Modify: `app/routers/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_confirm_score(client: AsyncClient, session: AsyncSession):
    """After submitting, the opponent confirms the score."""
    org_token, _ = await _register_and_get_token(client, "cf_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Confirm Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"cf_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match = resp.json()[0]
    match_id = match["id"]

    # Find tokens for both players
    a_token = next(tk for tk, pid in player_tokens if pid == match["player_a_id"])
    b_token = next(tk for tk, pid in player_tokens if pid == match["player_b_id"])

    # Player A submits
    await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {a_token}"},
        json={"sets": [{"set_number": 1, "score_a": 6, "score_b": 4}, {"set_number": 2, "score_a": 6, "score_b": 3}]},
    )

    # Player B confirms
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/confirm",
        headers={"Authorization": f"Bearer {b_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    assert resp.json()["confirmed_at"] is not None


@pytest.mark.asyncio
async def test_dispute_score(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "dp_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Dispute Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"dp_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match = resp.json()[0]
    match_id = match["id"]
    a_token = next(tk for tk, pid in player_tokens if pid == match["player_a_id"])
    b_token = next(tk for tk, pid in player_tokens if pid == match["player_b_id"])

    await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {a_token}"},
        json={"sets": [{"set_number": 1, "score_a": 6, "score_b": 4}, {"set_number": 2, "score_a": 6, "score_b": 3}]},
    )

    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/dispute",
        headers={"Authorization": f"Bearer {b_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "disputed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_events.py::test_confirm_score tests/test_events.py::test_dispute_score -v`

Expected: FAIL

- [ ] **Step 3: Add confirm, dispute, and auto-advance logic**

Add to `app/services/event.py`:

```python
from datetime import datetime, timezone


async def confirm_score(
    session: AsyncSession,
    match: EventMatch,
    user_id: uuid.UUID,
    lang: str = "en",
) -> EventMatch:
    from app.i18n import t

    if match.status != EventMatchStatus.SUBMITTED:
        raise ValueError(t("event.match_not_submitted", lang))

    if user_id not in (match.player_a_id, match.player_b_id):
        raise PermissionError(t("event.not_match_player", lang))

    if user_id == match.submitted_by:
        raise ValueError(t("event.cannot_confirm_own", lang))

    match.status = EventMatchStatus.CONFIRMED
    match.confirmed_at = datetime.now(timezone.utc)

    # Notify both players
    await create_notification(
        session,
        recipient_id=match.submitted_by,
        type=NotificationType.EVENT_SCORE_CONFIRMED,
        actor_id=user_id,
        target_type="event_match",
        target_id=match.id,
    )

    await session.flush()

    # Auto-advance for elimination tournaments
    event = await get_event_by_id(session, match.event_id)
    if event.event_type in (EventType.SINGLES_ELIMINATION, EventType.DOUBLES_ELIMINATION):
        await _advance_winner(session, event, match)

    # Check if all matches are done → complete event
    await _check_event_completion(session, event)

    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def dispute_score(
    session: AsyncSession,
    match: EventMatch,
    user_id: uuid.UUID,
    lang: str = "en",
) -> EventMatch:
    from app.i18n import t

    if match.status != EventMatchStatus.SUBMITTED:
        raise ValueError(t("event.match_not_submitted", lang))

    if user_id not in (match.player_a_id, match.player_b_id):
        raise PermissionError(t("event.not_match_player", lang))

    if user_id == match.submitted_by:
        raise ValueError(t("event.cannot_confirm_own", lang))

    match.status = EventMatchStatus.DISPUTED

    # Notify event organizer
    event = await get_event_by_id(session, match.event_id)
    await create_notification(
        session,
        recipient_id=event.creator_id,
        type=NotificationType.EVENT_SCORE_DISPUTED,
        actor_id=user_id,
        target_type="event_match",
        target_id=match.id,
    )

    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _advance_winner(session: AsyncSession, event: Event, match: EventMatch) -> None:
    """For elimination: fill the winner into the next round match."""
    all_matches = await get_event_matches(session, event.id)
    current_round = [m for m in all_matches if m.round == match.round]
    next_round = [m for m in all_matches if m.round == match.round + 1]

    if not next_round:
        return  # This was the final

    # Find this match's position in current round
    current_round.sort(key=lambda m: m.match_order)
    match_idx = next(i for i, m in enumerate(current_round) if m.id == match.id)

    # Determine which next-round match and slot
    next_match_idx = match_idx // 2
    slot = "a" if match_idx % 2 == 0 else "b"

    next_round.sort(key=lambda m: m.match_order)
    next_match = next_round[next_match_idx]

    if slot == "a":
        next_match.player_a_id = match.winner_id
    else:
        next_match.player_b_id = match.winner_id

    await session.flush()

    # If both players are now set, notify them
    if next_match.player_a_id and next_match.player_b_id:
        for pid in [next_match.player_a_id, next_match.player_b_id]:
            await create_notification(
                session,
                recipient_id=pid,
                type=NotificationType.EVENT_MATCH_READY,
                actor_id=event.creator_id,
                target_type="event_match",
                target_id=next_match.id,
            )

    # Notify eliminated loser
    loser_id = match.player_a_id if match.winner_id == match.player_b_id else match.player_b_id
    if loser_id:
        await create_notification(
            session,
            recipient_id=loser_id,
            type=NotificationType.EVENT_ELIMINATED,
            actor_id=event.creator_id,
            target_type="event",
            target_id=event.id,
        )
        # Mark loser as eliminated
        for p in event.participants:
            if p.user_id == loser_id:
                p.status = ParticipantStatus.ELIMINATED
                break


async def _check_event_completion(session: AsyncSession, event: Event) -> None:
    """Check if all matches are decided. If so, mark event as completed."""
    all_matches = await get_event_matches(session, event.id)
    all_decided = all(m.status in (EventMatchStatus.CONFIRMED, EventMatchStatus.WALKOVER) for m in all_matches)

    if all_decided and event.status == EventStatus.IN_PROGRESS:
        event.status = EventStatus.COMPLETED

        from app.services.chat import set_event_room_readonly
        await set_event_room_readonly(session, event_id=event.id)

        # Notify all participants
        for p in event.participants:
            if p.status in (ParticipantStatus.CONFIRMED, ParticipantStatus.ELIMINATED):
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.EVENT_COMPLETED,
                    actor_id=event.creator_id,
                    target_type="event",
                    target_id=event.id,
                )
```

- [ ] **Step 4: Add router endpoints**

Add to `app/routers/events.py` imports:

```python
from app.services.event import (
    confirm_score,
    create_event,
    dispute_score,
    get_event_by_id,
    get_event_matches,
    get_match_by_id,
    join_event,
    list_events,
    list_my_events,
    publish_event,
    remove_participant,
    start_event,
    submit_score,
    update_event,
    withdraw_from_event,
)
```

Add endpoints:

```python
@router.post("/matches/{match_id}/confirm", response_model=EventMatchResponse)
async def confirm_match_score(match_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    match = await get_match_by_id(session, uuid.UUID(match_id))
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.match_not_found", lang))

    try:
        match = await confirm_score(session, match, user.id, lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return match


@router.post("/matches/{match_id}/dispute", response_model=EventMatchResponse)
async def dispute_match_score(match_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    match = await get_match_by_id(session, uuid.UUID(match_id))
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.match_not_found", lang))

    try:
        match = await dispute_score(session, match, user.id, lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return match
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_events.py::test_confirm_score tests/test_events.py::test_dispute_score -v`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/event.py app/routers/events.py tests/test_events.py
git commit -m "feat(event): add score confirmation, dispute, and auto-advance"
```

---

### Task 13: Walkover + Organizer Score Override

**Files:**

- Modify: `app/services/event.py`
- Modify: `app/routers/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_walkover(client: AsyncClient, session: AsyncSession):
    """Submit a walkover — absent player gets credit penalty."""
    org_token, _ = await _register_and_get_token(client, "wo_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "WO Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"wo_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match = resp.json()[0]
    match_id = match["id"]
    a_token = next(tk for tk, pid in player_tokens if pid == match["player_a_id"])

    # Player A reports player B as absent
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/walkover",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"  # Needs opponent/organizer confirmation


@pytest.mark.asyncio
async def test_organizer_override_score(client: AsyncClient, session: AsyncSession):
    """Organizer can directly set/override a match score."""
    org_token, org_id = await _register_and_get_token(client, "ov_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Override Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"ov_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match = resp.json()[0]
    match_id = match["id"]

    # Organizer directly sets score (no confirmation needed)
    resp = await client.patch(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {org_token}"},
        json={"sets": [{"set_number": 1, "score_a": 6, "score_b": 2}, {"set_number": 2, "score_a": 6, "score_b": 1}]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_events.py::test_walkover tests/test_events.py::test_organizer_override_score -v`

Expected: FAIL

- [ ] **Step 3: Add walkover and organizer override logic**

Add to `app/services/event.py`:

```python
from app.models.credit import CreditReason
from app.services.credit import apply_credit_change


async def submit_walkover(
    session: AsyncSession,
    match: EventMatch,
    submitter_id: uuid.UUID,
    lang: str = "en",
) -> EventMatch:
    """Submit a walkover claim. Goes through same submitted→confirmed flow."""
    from app.i18n import t

    if match.status not in (EventMatchStatus.PENDING,):
        raise ValueError(t("event.walkover_already_decided", lang))

    if match.player_a_id is None or match.player_b_id is None:
        raise ValueError(t("event.match_not_ready", lang))

    if submitter_id not in (match.player_a_id, match.player_b_id):
        raise PermissionError(t("event.not_match_player", lang))

    # Submitter claims they showed up, opponent didn't → submitter wins
    match.winner_id = submitter_id
    match.status = EventMatchStatus.SUBMITTED
    match.submitted_by = submitter_id

    # Create a 0-0 set to record the walkover
    event_set = EventSet(
        match_id=match.id,
        set_number=1,
        score_a=0,
        score_b=0,
    )
    session.add(event_set)

    # Notify opponent
    opponent_id = match.player_b_id if submitter_id == match.player_a_id else match.player_a_id
    await create_notification(
        session,
        recipient_id=opponent_id,
        type=NotificationType.EVENT_WALKOVER,
        actor_id=submitter_id,
        target_type="event_match",
        target_id=match.id,
    )

    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def confirm_walkover(
    session: AsyncSession,
    match: EventMatch,
    user_id: uuid.UUID,
    lang: str = "en",
) -> EventMatch:
    """Confirm a walkover — applies credit penalty to absent player."""
    from app.i18n import t

    match = await confirm_score(session, match, user_id, lang)

    # Apply credit penalty to the loser (absent player)
    loser_id = match.player_a_id if match.winner_id == match.player_b_id else match.player_b_id
    if loser_id:
        result = await session.execute(select(User).where(User.id == loser_id))
        loser = result.scalar_one_or_none()
        if loser:
            await apply_credit_change(session, loser, CreditReason.NO_SHOW, description=f"Walkover in event match {match.id}")

        # Mark as withdrawn
        event = await get_event_by_id(session, match.event_id)
        for p in event.participants:
            if p.user_id == loser_id:
                p.status = ParticipantStatus.WITHDRAWN
                break
        await session.commit()

    match.status = EventMatchStatus.WALKOVER
    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def organizer_set_score(
    session: AsyncSession,
    match: EventMatch,
    organizer_id: uuid.UUID,
    sets_data: list[dict],
    lang: str = "en",
) -> EventMatch:
    """Organizer directly sets score — auto-confirmed, no dual confirmation needed."""
    from app.i18n import t

    event = await get_event_by_id(session, match.event_id)
    if event.creator_id != organizer_id:
        raise PermissionError(t("event.not_creator", lang))

    # Delete existing sets if overriding
    for s in list(match.sets):
        await session.delete(s)
    await session.flush()

    # Validate scores
    winner_side = validate_match_score(
        sets_data,
        games_per_set=event.games_per_set,
        num_sets=event.num_sets,
        match_tiebreak=event.match_tiebreak,
    )
    if winner_side is None:
        raise ValueError(t("event.score_invalid", lang))

    winner_id = match.player_a_id if winner_side == "a" else match.player_b_id

    for s in sets_data:
        event_set = EventSet(
            match_id=match.id,
            set_number=s["set_number"],
            score_a=s["score_a"],
            score_b=s["score_b"],
            tiebreak_a=s.get("tiebreak_a"),
            tiebreak_b=s.get("tiebreak_b"),
        )
        session.add(event_set)

    match.winner_id = winner_id
    match.status = EventMatchStatus.CONFIRMED
    match.confirmed_at = datetime.now(timezone.utc)

    await session.flush()

    # Auto-advance for elimination
    if event.event_type in (EventType.SINGLES_ELIMINATION, EventType.DOUBLES_ELIMINATION):
        await _advance_winner(session, event, match)

    await _check_event_completion(session, event)
    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()
```

- [ ] **Step 4: Add router endpoints**

Add to `app/routers/events.py` imports:

```python
from app.services.event import (
    confirm_score,
    create_event,
    dispute_score,
    get_event_by_id,
    get_event_matches,
    get_match_by_id,
    join_event,
    list_events,
    list_my_events,
    organizer_set_score,
    publish_event,
    remove_participant,
    start_event,
    submit_score,
    submit_walkover,
    update_event,
    withdraw_from_event,
)
```

Add endpoints:

```python
@router.post("/matches/{match_id}/walkover", response_model=EventMatchResponse)
async def submit_match_walkover(match_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    match = await get_match_by_id(session, uuid.UUID(match_id))
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.match_not_found", lang))

    try:
        match = await submit_walkover(session, match, user.id, lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return match


@router.patch("/matches/{match_id}/score", response_model=EventMatchResponse)
async def organizer_override_score(match_id: str, body: ScoreSubmitRequest, user: CurrentUser, session: DbSession, lang: Lang):
    match = await get_match_by_id(session, uuid.UUID(match_id))
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.match_not_found", lang))

    try:
        match = await organizer_set_score(session, match, user.id, [s.model_dump() for s in body.sets], lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return match
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_events.py::test_walkover tests/test_events.py::test_organizer_override_score -v`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/event.py app/routers/events.py tests/test_events.py
git commit -m "feat(event): add walkover, organizer score override"
```

---

### Task 14: Bracket + Standings Endpoints

**Files:**

- Modify: `app/services/event.py`
- Modify: `app/routers/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_get_bracket(client: AsyncClient, session: AsyncSession):
    """Get elimination bracket as tree structure."""
    org_token, _ = await _register_and_get_token(client, "br_org", ntrp="4.0")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Bracket Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    for i in range(4):
        tk, _ = await _register_and_get_token(client, f"br_p{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(
        f"/api/v1/events/{event_id}/bracket",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    bracket = resp.json()
    assert "rounds" in bracket
    assert len(bracket["rounds"]) >= 2  # At least 2 rounds for 4 players


@pytest.mark.asyncio
async def test_get_standings(client: AsyncClient, session: AsyncSession):
    """Get round-robin standings."""
    org_token, _ = await _register_and_get_token(client, "st_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Standings Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    for i in range(3):
        tk, _ = await _register_and_get_token(client, f"st_p{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(
        f"/api/v1/events/{event_id}/standings",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    standings = resp.json()
    assert len(standings) == 3  # 3 players in 1 group
    assert all("wins" in s and "losses" in s and "points" in s for s in standings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_events.py::test_get_bracket tests/test_events.py::test_get_standings -v`

Expected: FAIL

- [ ] **Step 3: Add bracket and standings service functions**

Add to `app/services/event.py`:

```python
async def get_bracket(session: AsyncSession, event_id: uuid.UUID) -> dict:
    """Return elimination bracket organized by rounds."""
    matches = await get_event_matches(session, event_id)

    rounds_dict: dict[int, list] = {}
    for m in matches:
        r = m.round
        if r not in rounds_dict:
            rounds_dict[r] = []
        rounds_dict[r].append({
            "id": str(m.id),
            "match_order": m.match_order,
            "player_a_id": str(m.player_a_id) if m.player_a_id else None,
            "player_b_id": str(m.player_b_id) if m.player_b_id else None,
            "winner_id": str(m.winner_id) if m.winner_id else None,
            "status": m.status.value,
            "sets": [
                {
                    "set_number": s.set_number,
                    "score_a": s.score_a,
                    "score_b": s.score_b,
                    "tiebreak_a": s.tiebreak_a,
                    "tiebreak_b": s.tiebreak_b,
                }
                for s in sorted(m.sets, key=lambda s: s.set_number)
            ],
        })

    rounds = []
    for r in sorted(rounds_dict.keys()):
        rounds.append({
            "round": r,
            "matches": sorted(rounds_dict[r], key=lambda m: m["match_order"]),
        })

    return {"rounds": rounds}


async def get_standings(session: AsyncSession, event_id: uuid.UUID) -> list[dict]:
    """Calculate round-robin standings from confirmed matches."""
    event = await get_event_by_id(session, event_id)
    matches = await get_event_matches(session, event_id)

    # Build standings per participant
    stats: dict[uuid.UUID, dict] = {}
    for p in event.participants:
        if p.status in (ParticipantStatus.CONFIRMED, ParticipantStatus.REGISTERED):
            stats[p.user_id] = {
                "user_id": p.user_id,
                "nickname": p.user.nickname,
                "group_name": p.group_name or "A",
                "wins": 0,
                "losses": 0,
                "points": 0,
                "sets_won": 0,
                "sets_lost": 0,
            }

    for m in matches:
        if m.status not in (EventMatchStatus.CONFIRMED, EventMatchStatus.WALKOVER):
            continue
        if m.winner_id is None:
            continue

        loser_id = m.player_a_id if m.winner_id == m.player_b_id else m.player_b_id

        if m.winner_id in stats:
            stats[m.winner_id]["wins"] += 1
            stats[m.winner_id]["points"] += 3

        if loser_id and loser_id in stats:
            stats[loser_id]["losses"] += 1

        # Count sets won/lost
        for s in m.sets:
            if s.score_a == 0 and s.score_b == 0:
                continue  # Walkover set
            a_won = s.score_a > s.score_b
            if m.player_a_id in stats:
                stats[m.player_a_id]["sets_won"] += 1 if a_won else 0
                stats[m.player_a_id]["sets_lost"] += 0 if a_won else 1
            if m.player_b_id in stats:
                stats[m.player_b_id]["sets_won"] += 0 if a_won else 1
                stats[m.player_b_id]["sets_lost"] += 1 if a_won else 0

    # Sort by points desc, then set difference
    result = sorted(
        stats.values(),
        key=lambda s: (-s["points"], -(s["sets_won"] - s["sets_lost"])),
    )
    return result
```

- [ ] **Step 4: Add router endpoints**

Add to `app/routers/events.py` imports:

```python
from app.services.event import (
    confirm_score,
    create_event,
    dispute_score,
    get_bracket,
    get_event_by_id,
    get_event_matches,
    get_match_by_id,
    get_standings,
    join_event,
    list_events,
    list_my_events,
    organizer_set_score,
    publish_event,
    remove_participant,
    start_event,
    submit_score,
    submit_walkover,
    update_event,
    withdraw_from_event,
)
```

Add endpoints:

```python
@router.get("/{event_id}/bracket")
async def get_event_bracket(event_id: str, session: DbSession, user: CurrentUser, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    return await get_bracket(session, event.id)


@router.get("/{event_id}/standings", response_model=list[StandingsEntry])
async def get_event_standings(event_id: str, session: DbSession, user: CurrentUser, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    return await get_standings(session, event.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_events.py::test_get_bracket tests/test_events.py::test_get_standings -v`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/event.py app/routers/events.py tests/test_events.py
git commit -m "feat(event): add bracket and standings endpoints"
```

---

### Task 15: Cancel Event + Update conftest

**Files:**

- Modify: `app/services/event.py`
- Modify: `app/routers/events.py`
- Modify: `tests/test_events.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_events.py`:

```python
@pytest.mark.asyncio
async def test_cancel_event(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "can_org")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Cancel Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Join a player
    player_token, _ = await _register_and_get_token(client, "can_p1", ntrp="3.5")
    await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {player_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/cancel",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py::test_cancel_event -v`

Expected: FAIL

- [ ] **Step 3: Add cancel logic**

Add to `app/services/event.py`:

```python
async def cancel_event(
    session: AsyncSession,
    event: Event,
    lang: str = "en",
) -> Event:
    from app.services.chat import set_event_room_readonly

    event.status = EventStatus.CANCELLED

    # Set chat room readonly if exists
    await set_event_room_readonly(session, event_id=event.id)

    # Notify all participants
    for p in event.participants:
        if p.status in (ParticipantStatus.REGISTERED, ParticipantStatus.CONFIRMED):
            await create_notification(
                session,
                recipient_id=p.user_id,
                type=NotificationType.EVENT_CANCELLED,
                actor_id=event.creator_id,
                target_type="event",
                target_id=event.id,
            )

    await session.commit()
    event = await get_event_by_id(session, event.id)
    return event
```

- [ ] **Step 4: Add router endpoint**

Add `cancel_event` to the router imports and add endpoint:

```python
@router.post("/{event_id}/cancel", response_model=EventDetailResponse)
async def cancel_existing_event(event_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    if event.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("event.not_creator", lang))

    event = await cancel_event(session, event, lang)
    return _event_to_response(event, include_participants=True)
```

- [ ] **Step 5: Update conftest.py to import event models**

In `tests/conftest.py`, update the import line to include event models:

```python
from app.models import Booking, BookingParticipant, Block, Court, CreditLog, Follow, Notification, Report, Review, User, UserAuth, MatchPreference, MatchTimeSlot, MatchPreferenceCourt, MatchProposal, ChatRoom, ChatParticipant, Message, Event, EventParticipant, EventMatch, EventSet  # noqa: F401
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py::test_cancel_event -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/event.py app/routers/events.py tests/test_events.py tests/conftest.py
git commit -m "feat(event): add cancel event, update conftest with event models"
```

---

### Task 16: Update CLAUDE.md + Full Test Suite

**Files:**

- Modify: `CLAUDE.md`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`

Verify all existing tests still pass alongside the new event tests.

- [ ] **Step 2: Update CLAUDE.md module table**

Add the Event module to the modules table in `CLAUDE.md`:

```
| Event 赛事 | `event.py` | Elimination + round-robin tournaments. Lifecycle: `draft → open → in_progress → completed/cancelled`. Seeded draws, structured scoring, dual-confirmation. |
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md tests/test_events.py
git commit -m "docs: update CLAUDE.md with event system module"
```
