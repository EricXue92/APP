# Smart Matching (智能匹配) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a smart matching system that pairs compatible tennis players (user-to-user) and recommends open bookings (user-to-booking), using weighted scoring with a proposal-based confirmation flow.

**Architecture:** Two new services — `matching.py` (preference CRUD, scoring, candidate search, passive notifications) and `match_proposal.py` (proposal lifecycle, auto-booking on accept). One new model file with four tables. One router exposing all endpoints under `/api/v1/matching/`. TDD throughout.

**Tech Stack:** SQLAlchemy async, PostgreSQL, FastAPI, pytest-asyncio, Pydantic v2

---

### Task 1: Models — MatchPreference, MatchTimeSlot, MatchPreferenceCourt, MatchProposal

**Files:**
- Create: `app/models/matching.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/notification.py`

- [ ] **Step 1: Create the matching models file**

```python
# app/models/matching.py
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
```

- [ ] **Step 2: Add new notification types to `app/models/notification.py`**

Add four new values to the `NotificationType` enum, after `IDEAL_PLAYER_LOST`:

```python
    MATCH_PROPOSAL_RECEIVED = "match_proposal_received"
    MATCH_PROPOSAL_ACCEPTED = "match_proposal_accepted"
    MATCH_PROPOSAL_REJECTED = "match_proposal_rejected"
    MATCH_SUGGESTION = "match_suggestion"
```

- [ ] **Step 3: Register models in `app/models/__init__.py`**

Replace the file contents with:

```python
from app.models.user import User, UserAuth
from app.models.credit import CreditLog
from app.models.court import Court
from app.models.booking import Booking, BookingParticipant
from app.models.review import Review
from app.models.block import Block
from app.models.report import Report
from app.models.follow import Follow
from app.models.notification import Notification
from app.models.matching import MatchPreference, MatchTimeSlot, MatchPreferenceCourt, MatchProposal

__all__ = [
    "User", "UserAuth", "CreditLog", "Court", "Booking", "BookingParticipant",
    "Review", "Block", "Report", "Follow", "Notification",
    "MatchPreference", "MatchTimeSlot", "MatchPreferenceCourt", "MatchProposal",
]
```

- [ ] **Step 4: Update `tests/conftest.py` to import new models**

Change the import line to include matching models:

```python
from app.models import Booking, BookingParticipant, Block, Court, CreditLog, Follow, Notification, Report, Review, User, UserAuth, MatchPreference, MatchTimeSlot, MatchPreferenceCourt, MatchProposal  # noqa: F401
```

- [ ] **Step 5: Generate Alembic migration**

Run: `uv run alembic revision --autogenerate -m "add matching tables"`

- [ ] **Step 6: Apply migration and verify**

Run: `uv run alembic upgrade head`

- [ ] **Step 7: Commit**

```bash
git add app/models/matching.py app/models/__init__.py app/models/notification.py tests/conftest.py alembic/versions/
git commit -m "feat: add matching data models and notification types"
```

---

### Task 2: Pydantic schemas for matching

**Files:**
- Create: `app/schemas/matching.py`

- [ ] **Step 1: Create the schemas file**

```python
# app/schemas/matching.py
import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator


class TimeSlotRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: time
    end_time: time

    @field_validator("start_time", "end_time")
    @classmethod
    def must_be_half_hour(cls, v: time) -> time:
        if v.minute not in (0, 30):
            raise ValueError("Time must be on the hour or half hour")
        return v


class TimeSlotResponse(BaseModel):
    id: uuid.UUID
    day_of_week: int
    start_time: time
    end_time: time

    model_config = {"from_attributes": True}


class PreferenceCreateRequest(BaseModel):
    match_type: str = Field(default="any", pattern=r"^(singles|doubles|any)$")
    min_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    max_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    gender_preference: str = Field(default="any", pattern=r"^(male_only|female_only|any)$")
    max_distance_km: float | None = Field(default=None, ge=0)
    time_slots: list[TimeSlotRequest] = Field(..., min_length=1)
    court_ids: list[uuid.UUID] = Field(default_factory=list)


class PreferenceResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    match_type: str
    min_ntrp: str
    max_ntrp: str
    gender_preference: str
    max_distance_km: float | None
    is_active: bool
    last_active_at: datetime
    time_slots: list[TimeSlotResponse]
    court_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class ToggleResponse(BaseModel):
    is_active: bool


class CandidateResponse(BaseModel):
    user_id: uuid.UUID
    nickname: str
    gender: str
    ntrp_level: str
    ntrp_label: str
    credit_score: int
    is_ideal_player: bool
    city: str
    score: float


class BookingRecommendationResponse(BaseModel):
    booking_id: uuid.UUID
    creator_id: uuid.UUID
    creator_nickname: str
    court_id: uuid.UUID
    court_name: str
    match_type: str
    play_date: date
    start_time: time
    end_time: time
    min_ntrp: str
    max_ntrp: str
    gender_requirement: str
    score: float


class ProposalCreateRequest(BaseModel):
    target_id: uuid.UUID
    court_id: uuid.UUID
    match_type: str = Field(default="singles", pattern=r"^(singles|doubles)$")
    play_date: date
    start_time: time
    end_time: time
    message: str | None = Field(default=None, max_length=500)


class ProposalResponse(BaseModel):
    id: uuid.UUID
    proposer_id: uuid.UUID
    proposer_nickname: str
    target_id: uuid.UUID
    target_nickname: str
    court_id: uuid.UUID
    court_name: str
    match_type: str
    play_date: date
    start_time: time
    end_time: time
    message: str | None
    status: str
    created_at: datetime
    responded_at: datetime | None


class ProposalRespondRequest(BaseModel):
    status: str = Field(..., pattern=r"^(accepted|rejected)$")
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/matching.py
git commit -m "feat: add matching Pydantic schemas"
```

---

### Task 3: i18n messages for matching

**Files:**
- Modify: `app/i18n.py`

- [ ] **Step 1: Add matching-related messages to `_MESSAGES` dict in `app/i18n.py`**

Add these entries at the end of the `_MESSAGES` dict (before the closing `}`):

```python
    "matching.preference_exists": {
        "zh-Hans": "匹配偏好已存在",
        "zh-Hant": "配對偏好已存在",
        "en": "Match preference already exists",
    },
    "matching.preference_not_found": {
        "zh-Hans": "匹配偏好未找到",
        "zh-Hant": "配對偏好未找到",
        "en": "Match preference not found",
    },
    "matching.preference_inactive": {
        "zh-Hans": "匹配功能未激活",
        "zh-Hant": "配對功能未啟用",
        "en": "Matching is not active",
    },
    "matching.proposal_daily_cap": {
        "zh-Hans": "今日发送配对请求已达上限",
        "zh-Hant": "今日發送配對請求已達上限",
        "en": "Daily proposal limit reached",
    },
    "matching.cannot_propose_self": {
        "zh-Hans": "不能向自己发送配对请求",
        "zh-Hant": "不能向自己發送配對請求",
        "en": "Cannot send a proposal to yourself",
    },
    "matching.proposal_not_found": {
        "zh-Hans": "配对请求未找到",
        "zh-Hant": "配對請求未找到",
        "en": "Proposal not found",
    },
    "matching.proposal_not_pending": {
        "zh-Hans": "配对请求已处理",
        "zh-Hant": "配對請求已處理",
        "en": "Proposal is no longer pending",
    },
    "matching.proposal_not_target": {
        "zh-Hans": "只有接收方才能回应",
        "zh-Hant": "只有接收方才能回應",
        "en": "Only the proposal target can respond",
    },
    "matching.duplicate_pending": {
        "zh-Hans": "你已向该用户发送了配对请求",
        "zh-Hant": "你已向該用戶發送了配對請求",
        "en": "You already have a pending proposal to this user",
    },
    "matching.proposer_suspended": {
        "zh-Hans": "对方账号已被停用",
        "zh-Hant": "對方帳號已被停用",
        "en": "Proposer's account has been suspended",
    },
    "matching.target_not_found": {
        "zh-Hans": "目标用户不存在",
        "zh-Hant": "目標用戶不存在",
        "en": "Target user not found",
    },
```

- [ ] **Step 2: Commit**

```bash
git add app/i18n.py
git commit -m "feat: add matching i18n messages"
```

---

### Task 4: Matching service — preference CRUD

**Files:**
- Create: `app/services/matching.py`
- Create: `tests/test_matching.py`

- [ ] **Step 1: Write failing tests for preference CRUD**

```python
# tests/test_matching.py
import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.user import AuthProvider, User


async def _register_and_get_token(
    client: AsyncClient, username: str, gender: str = "male", ntrp: str = "3.5"
) -> tuple[str, str]:
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


async def _seed_court(session: AsyncSession, name: str = "Test Court") -> Court:
    court = Court(
        name=name,
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Preference CRUD Tests ---


@pytest.mark.asyncio
async def test_create_preference(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "match1")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/matching/preferences",
        headers=_auth(token),
        json={
            "match_type": "singles",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_preference": "any",
            "time_slots": [
                {"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"},
                {"day_of_week": 6, "start_time": "14:00:00", "end_time": "17:00:00"},
            ],
            "court_ids": [str(court.id)],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["match_type"] == "singles"
    assert data["is_active"] is True
    assert len(data["time_slots"]) == 2
    assert data["court_ids"] == [str(court.id)]


@pytest.mark.asyncio
async def test_create_preference_duplicate(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match2")

    body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    resp1 = await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_preference_invalid_time(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match3")

    resp = await client.post(
        "/api/v1/matching/preferences",
        headers=_auth(token),
        json={
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "time_slots": [{"day_of_week": 5, "start_time": "09:15:00", "end_time": "12:00:00"}],
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_preference(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match4")

    body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)

    resp = await client.get("/api/v1/matching/preferences", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["min_ntrp"] == "3.0"


@pytest.mark.asyncio
async def test_get_preference_not_found(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match5")

    resp = await client.get("/api/v1/matching/preferences", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_preference(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match6")
    court = await _seed_court(session)

    body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)

    resp = await client.put(
        "/api/v1/matching/preferences",
        headers=_auth(token),
        json={
            "min_ntrp": "3.5",
            "max_ntrp": "4.5",
            "time_slots": [{"day_of_week": 6, "start_time": "14:00:00", "end_time": "17:00:00"}],
            "court_ids": [str(court.id)],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["min_ntrp"] == "3.5"
    assert len(data["time_slots"]) == 1
    assert data["time_slots"][0]["day_of_week"] == 6
    assert data["court_ids"] == [str(court.id)]


@pytest.mark.asyncio
async def test_toggle_preference(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match7")

    body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)

    resp = await client.patch("/api/v1/matching/preferences/toggle", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = await client.patch("/api/v1/matching/preferences/toggle", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_matching.py -v`
Expected: FAIL — `app.services.matching` module does not exist

- [ ] **Step 3: Write the matching service (preference CRUD)**

```python
# app/services/matching.py
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.matching import (
    GenderPreference,
    MatchPreference,
    MatchPreferenceCourt,
    MatchTimeSlot,
    MatchTypePreference,
)


async def create_preference(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    match_type: str = "any",
    min_ntrp: str,
    max_ntrp: str,
    gender_preference: str = "any",
    max_distance_km: float | None = None,
    time_slots: list[dict],
    court_ids: list[uuid.UUID],
) -> MatchPreference:
    # Check for existing preference
    existing = await session.execute(
        select(MatchPreference).where(MatchPreference.user_id == user_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError("preference_exists")

    pref = MatchPreference(
        user_id=user_id,
        match_type=MatchTypePreference(match_type),
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_preference=GenderPreference(gender_preference),
        max_distance_km=max_distance_km,
    )
    session.add(pref)
    await session.flush()

    for slot in time_slots:
        ts = MatchTimeSlot(
            preference_id=pref.id,
            day_of_week=slot["day_of_week"],
            start_time=slot["start_time"],
            end_time=slot["end_time"],
        )
        session.add(ts)

    for court_id in court_ids:
        pc = MatchPreferenceCourt(preference_id=pref.id, court_id=court_id)
        session.add(pc)

    await session.commit()
    return await get_preference_by_user(session, user_id)


async def get_preference_by_user(
    session: AsyncSession, user_id: uuid.UUID
) -> MatchPreference | None:
    result = await session.execute(
        select(MatchPreference)
        .options(
            selectinload(MatchPreference.time_slots),
            selectinload(MatchPreference.preferred_courts),
        )
        .where(MatchPreference.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_preference(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    match_type: str = "any",
    min_ntrp: str,
    max_ntrp: str,
    gender_preference: str = "any",
    max_distance_km: float | None = None,
    time_slots: list[dict],
    court_ids: list[uuid.UUID],
) -> MatchPreference:
    pref = await get_preference_by_user(session, user_id)
    if pref is None:
        raise ValueError("preference_not_found")

    pref.match_type = MatchTypePreference(match_type)
    pref.min_ntrp = min_ntrp
    pref.max_ntrp = max_ntrp
    pref.gender_preference = GenderPreference(gender_preference)
    pref.max_distance_km = max_distance_km

    # Replace time slots
    for ts in list(pref.time_slots):
        await session.delete(ts)
    await session.flush()

    for slot in time_slots:
        ts = MatchTimeSlot(
            preference_id=pref.id,
            day_of_week=slot["day_of_week"],
            start_time=slot["start_time"],
            end_time=slot["end_time"],
        )
        session.add(ts)

    # Replace preferred courts
    for pc in list(pref.preferred_courts):
        await session.delete(pc)
    await session.flush()

    for court_id in court_ids:
        pc = MatchPreferenceCourt(preference_id=pref.id, court_id=court_id)
        session.add(pc)

    await session.commit()
    return await get_preference_by_user(session, user_id)


async def toggle_preference(
    session: AsyncSession, user_id: uuid.UUID
) -> MatchPreference:
    pref = await get_preference_by_user(session, user_id)
    if pref is None:
        raise ValueError("preference_not_found")

    pref.is_active = not pref.is_active
    if pref.is_active:
        pref.last_active_at = datetime.now(timezone.utc)
    await session.commit()
    return await get_preference_by_user(session, user_id)
```

- [ ] **Step 4: Create the matching router (preference endpoints only)**

```python
# app/routers/matching.py
from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.matching import (
    PreferenceCreateRequest,
    PreferenceResponse,
    TimeSlotResponse,
    ToggleResponse,
)
from app.services.matching import (
    create_preference,
    get_preference_by_user,
    toggle_preference,
    update_preference,
)

router = APIRouter()


def _pref_to_response(pref) -> PreferenceResponse:
    return PreferenceResponse(
        id=pref.id,
        user_id=pref.user_id,
        match_type=pref.match_type.value,
        min_ntrp=pref.min_ntrp,
        max_ntrp=pref.max_ntrp,
        gender_preference=pref.gender_preference.value,
        max_distance_km=pref.max_distance_km,
        is_active=pref.is_active,
        last_active_at=pref.last_active_at,
        time_slots=[
            TimeSlotResponse(
                id=ts.id,
                day_of_week=ts.day_of_week,
                start_time=ts.start_time,
                end_time=ts.end_time,
            )
            for ts in pref.time_slots
        ],
        court_ids=[pc.court_id for pc in pref.preferred_courts],
        created_at=pref.created_at,
        updated_at=pref.updated_at,
    )


@router.post("/preferences", response_model=PreferenceResponse, status_code=status.HTTP_201_CREATED)
async def create_match_preference(body: PreferenceCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        pref = await create_preference(
            session,
            user_id=user.id,
            match_type=body.match_type,
            min_ntrp=body.min_ntrp,
            max_ntrp=body.max_ntrp,
            gender_preference=body.gender_preference,
            max_distance_km=body.max_distance_km,
            time_slots=[s.model_dump() for s in body.time_slots],
            court_ids=body.court_ids,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("matching.preference_exists", lang))
    return _pref_to_response(pref)


@router.get("/preferences", response_model=PreferenceResponse)
async def get_match_preference(user: CurrentUser, session: DbSession, lang: Lang):
    pref = await get_preference_by_user(session, user.id)
    if pref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    return _pref_to_response(pref)


@router.put("/preferences", response_model=PreferenceResponse)
async def update_match_preference(body: PreferenceCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        pref = await update_preference(
            session,
            user_id=user.id,
            match_type=body.match_type,
            min_ntrp=body.min_ntrp,
            max_ntrp=body.max_ntrp,
            gender_preference=body.gender_preference,
            max_distance_km=body.max_distance_km,
            time_slots=[s.model_dump() for s in body.time_slots],
            court_ids=body.court_ids,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    return _pref_to_response(pref)


@router.patch("/preferences/toggle", response_model=ToggleResponse)
async def toggle_match_preference(user: CurrentUser, session: DbSession, lang: Lang):
    try:
        pref = await toggle_preference(session, user.id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    return ToggleResponse(is_active=pref.is_active)
```

- [ ] **Step 5: Register the matching router in `app/main.py`**

Add the import and `include_router` call. After the `reports` import, add `matching`:

```python
from app.routers import auth, assistant, blocks, bookings, courts, follows, matching, notifications, reports, reviews, users
```

And add this line after the reports admin router registration:

```python
app.include_router(matching.router, prefix="/api/v1/matching", tags=["matching"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_matching.py -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/matching.py app/routers/matching.py app/main.py tests/test_matching.py
git commit -m "feat: add matching preference CRUD with tests"
```

---

### Task 5: Scoring algorithm

**Files:**
- Modify: `app/services/matching.py`
- Modify: `tests/test_matching.py`

- [ ] **Step 1: Write failing tests for scoring**

Add these tests to `tests/test_matching.py`:

```python
from app.models.court import Court, CourtType, SurfaceType
from app.models.matching import MatchPreference, MatchTimeSlot, MatchPreferenceCourt, MatchTypePreference, GenderPreference
from app.models.user import Gender, User
from app.services.matching import compute_match_score
from app.services.user import create_user_with_auth
from app.models.user import AuthProvider


async def _create_user_direct(session: AsyncSession, username: str, **kwargs) -> User:
    defaults = {
        "nickname": f"Player_{username}",
        "gender": "male",
        "city": "Hong Kong",
        "ntrp_level": "3.5",
        "language": "en",
        "provider": AuthProvider.USERNAME,
        "provider_user_id": username,
        "password": "test1234",
    }
    defaults.update(kwargs)
    return await create_user_with_auth(session, **defaults)


async def _create_preference_direct(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    min_ntrp: str = "3.0",
    max_ntrp: str = "4.0",
    slots: list[tuple[int, str, str]] | None = None,
    court_ids: list[uuid.UUID] | None = None,
    gender_preference: str = "any",
    match_type: str = "singles",
) -> MatchPreference:
    pref = MatchPreference(
        user_id=user_id,
        match_type=MatchTypePreference(match_type),
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_preference=GenderPreference(gender_preference),
    )
    session.add(pref)
    await session.flush()

    if slots is None:
        slots = [(5, "09:00", "12:00")]
    for day, start, end in slots:
        ts = MatchTimeSlot(
            preference_id=pref.id,
            day_of_week=day,
            start_time=time.fromisoformat(start),
            end_time=time.fromisoformat(end),
        )
        session.add(ts)

    for cid in (court_ids or []):
        pc = MatchPreferenceCourt(preference_id=pref.id, court_id=cid)
        session.add(pc)

    await session.commit()
    await session.refresh(pref)
    return pref


# --- Scoring Tests ---


@pytest.mark.asyncio
async def test_score_perfect_match(client: AsyncClient, session: AsyncSession):
    """Two users with identical preferences should get a high score."""
    user_a = await _create_user_direct(session, "score_a")
    user_b = await _create_user_direct(session, "score_b")
    court = await _seed_court(session)

    pref_a = await _create_preference_direct(session, user_a.id, court_ids=[court.id])
    pref_b = await _create_preference_direct(session, user_b.id, court_ids=[court.id])

    score = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    assert score is not None
    assert score >= 80  # High score for perfect overlap


@pytest.mark.asyncio
async def test_score_ntrp_too_far(client: AsyncClient, session: AsyncSession):
    """NTRP gap > 1.5 should return None (filtered out)."""
    user_a = await _create_user_direct(session, "score_c", ntrp_level="2.0")
    user_b = await _create_user_direct(session, "score_d", ntrp_level="4.5")

    pref_a = await _create_preference_direct(session, user_a.id, min_ntrp="1.5", max_ntrp="2.5")
    pref_b = await _create_preference_direct(session, user_b.id, min_ntrp="4.0", max_ntrp="5.0")

    score = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    assert score is None


@pytest.mark.asyncio
async def test_score_no_time_overlap(client: AsyncClient, session: AsyncSession):
    """No overlapping time slots should return None."""
    user_a = await _create_user_direct(session, "score_e")
    user_b = await _create_user_direct(session, "score_f")

    pref_a = await _create_preference_direct(session, user_a.id, slots=[(0, "09:00", "12:00")])  # Monday
    pref_b = await _create_preference_direct(session, user_b.id, slots=[(5, "14:00", "17:00")])  # Saturday

    score = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    assert score is None


@pytest.mark.asyncio
async def test_score_gender_filter(client: AsyncClient, session: AsyncSession):
    """Gender mismatch with preference should return None."""
    user_a = await _create_user_direct(session, "score_g", gender="male")
    user_b = await _create_user_direct(session, "score_h", gender="male")

    pref_a = await _create_preference_direct(session, user_a.id, gender_preference="female_only")
    pref_b = await _create_preference_direct(session, user_b.id)

    score = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    assert score is None


@pytest.mark.asyncio
async def test_score_ideal_player_bonus(client: AsyncClient, session: AsyncSession):
    """Ideal player should score higher than non-ideal with same stats."""
    user_a = await _create_user_direct(session, "score_i")
    user_b = await _create_user_direct(session, "score_j")
    user_c = await _create_user_direct(session, "score_k")
    user_c.is_ideal_player = True
    await session.commit()

    court = await _seed_court(session)
    pref_a = await _create_preference_direct(session, user_a.id, court_ids=[court.id])
    pref_b = await _create_preference_direct(session, user_b.id, court_ids=[court.id])
    pref_c = await _create_preference_direct(session, user_c.id, court_ids=[court.id])

    score_b = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    score_c = await compute_match_score(session, user_a, pref_a, user_c, pref_c)
    assert score_c > score_b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_matching.py::test_score_perfect_match -v`
Expected: FAIL — `compute_match_score` not found

- [ ] **Step 3: Implement the scoring algorithm in `app/services/matching.py`**

Add the `_ntrp_to_float` import and `compute_match_score` function:

```python
import math
from app.models.court import Court
from app.models.user import Gender, User
from app.services.booking import _ntrp_to_float


def _time_overlap_minutes(start_a: time, end_a: time, start_b: time, end_b: time) -> int:
    """Calculate overlap in minutes between two time ranges on the same day."""
    latest_start = max(start_a, start_b)
    earliest_end = min(end_a, end_b)
    if latest_start >= earliest_end:
        return 0
    delta = datetime.combine(datetime.min, earliest_end) - datetime.combine(datetime.min, latest_start)
    return int(delta.total_seconds() / 60)


def _compute_time_overlap_ratio(slots_a: list[MatchTimeSlot], slots_b: list[MatchTimeSlot]) -> float:
    """Compute the ratio of overlapping time to total available time for user A."""
    total_overlap = 0
    total_a = 0

    for sa in slots_a:
        slot_minutes = (
            datetime.combine(datetime.min, sa.end_time)
            - datetime.combine(datetime.min, sa.start_time)
        ).total_seconds() / 60
        total_a += slot_minutes

        for sb in slots_b:
            if sa.day_of_week == sb.day_of_week:
                total_overlap += _time_overlap_minutes(sa.start_time, sa.end_time, sb.start_time, sb.end_time)

    if total_a == 0:
        return 0.0
    return min(total_overlap / total_a, 1.0)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


async def compute_match_score(
    session: AsyncSession,
    user_a: User,
    pref_a: MatchPreference,
    user_b: User,
    pref_b: MatchPreference,
) -> float | None:
    """
    Compute match score between two users (0-100).
    Returns None if hard-filtered (incompatible).
    """
    # --- Hard filters ---

    # Gender check: A's preference vs B's gender and vice versa
    if pref_a.gender_preference == GenderPreference.MALE_ONLY and user_b.gender != Gender.MALE:
        return None
    if pref_a.gender_preference == GenderPreference.FEMALE_ONLY and user_b.gender != Gender.FEMALE:
        return None
    if pref_b.gender_preference == GenderPreference.MALE_ONLY and user_a.gender != Gender.MALE:
        return None
    if pref_b.gender_preference == GenderPreference.FEMALE_ONLY and user_a.gender != Gender.FEMALE:
        return None

    # NTRP gap check
    ntrp_a = _ntrp_to_float(user_a.ntrp_level)
    ntrp_b = _ntrp_to_float(user_b.ntrp_level)
    ntrp_gap = abs(ntrp_a - ntrp_b)
    if ntrp_gap > 1.5:
        return None

    # Time overlap check
    time_ratio = _compute_time_overlap_ratio(pref_a.time_slots, pref_b.time_slots)
    if time_ratio == 0:
        return None

    # --- Soft scoring ---
    weights = {"ntrp": 35, "time": 25, "court": 20, "credit": 10, "gender": 5, "ideal": 5}

    # NTRP score: full at ±0.5, linear decay to 0 at ±1.5
    if ntrp_gap <= 0.5:
        ntrp_score = 1.0
    else:
        ntrp_score = max(0.0, 1.0 - (ntrp_gap - 0.5) / 1.0)

    # Time score
    time_score = time_ratio

    # Court proximity score
    courts_a = pref_a.preferred_courts
    courts_b = pref_b.preferred_courts
    court_a_ids = {pc.court_id for pc in courts_a}
    court_b_ids = {pc.court_id for pc in courts_b}

    if not court_a_ids and not court_b_ids:
        # Neither has preferred courts — redistribute court weight
        court_score = 0.0
        redistributed = weights["court"]
        total_other = weights["ntrp"] + weights["time"] + weights["credit"] + weights["gender"] + weights["ideal"]
        weights["ntrp"] += redistributed * weights["ntrp"] / total_other
        weights["time"] += redistributed * weights["time"] / total_other
        weights["credit"] += redistributed * weights["credit"] / total_other
        weights["gender"] += redistributed * weights["gender"] / total_other
        weights["ideal"] += redistributed * weights["ideal"] / total_other
        weights["court"] = 0
    elif court_a_ids & court_b_ids:
        court_score = 1.0
    else:
        # Compute distance between nearest courts if both have lat/lng
        court_a_objs = []
        court_b_objs = []
        for pc in courts_a:
            result = await session.get(Court, pc.court_id)
            if result and result.latitude and result.longitude:
                court_a_objs.append(result)
        for pc in courts_b:
            result = await session.get(Court, pc.court_id)
            if result and result.latitude and result.longitude:
                court_b_objs.append(result)

        if court_a_objs and court_b_objs:
            min_dist = min(
                _haversine_km(ca.latitude, ca.longitude, cb.latitude, cb.longitude)
                for ca in court_a_objs
                for cb in court_b_objs
            )
            max_dist = pref_a.max_distance_km or 20.0  # default 20km
            court_score = max(0.0, 1.0 - min_dist / max_dist)
        else:
            court_score = 0.5  # Partial info, give neutral score

    # Credit score
    credit_score = user_b.credit_score / 100.0

    # Gender score (passed hard filter, so full score)
    gender_score = 1.0

    # Ideal player score
    ideal_score = 1.0 if user_b.is_ideal_player else 0.0

    total = (
        weights["ntrp"] * ntrp_score
        + weights["time"] * time_score
        + weights["court"] * court_score
        + weights["credit"] * credit_score
        + weights["gender"] * gender_score
        + weights["ideal"] * ideal_score
    )

    return round(total, 2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_matching.py -v -k "score"`
Expected: All 5 scoring tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/matching.py tests/test_matching.py
git commit -m "feat: add matching scoring algorithm with tests"
```

---

### Task 6: Candidate search endpoints

**Files:**
- Modify: `app/services/matching.py`
- Modify: `app/routers/matching.py`
- Modify: `tests/test_matching.py`

- [ ] **Step 1: Write failing tests for candidate search**

Add to `tests/test_matching.py`:

```python
from sqlalchemy import update


@pytest.mark.asyncio
async def test_search_candidates(client: AsyncClient, session: AsyncSession):
    """Should return compatible candidates sorted by score."""
    token_a, uid_a = await _register_and_get_token(client, "cand_a", ntrp="3.5")
    token_b, uid_b = await _register_and_get_token(client, "cand_b", ntrp="3.5")
    court = await _seed_court(session)

    # Both create preferences with overlapping time and same court
    pref_body = {
        "match_type": "singles",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
        "court_ids": [str(court.id)],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token_a), json=pref_body)
    await client.post("/api/v1/matching/preferences", headers=_auth(token_b), json=pref_body)

    resp = await client.get("/api/v1/matching/candidates", headers=_auth(token_a))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == uid_b
    assert data[0]["score"] > 0


@pytest.mark.asyncio
async def test_search_candidates_filters_blocked(client: AsyncClient, session: AsyncSession):
    """Blocked users should not appear in candidates."""
    token_a, uid_a = await _register_and_get_token(client, "cand_c", ntrp="3.5")
    token_b, uid_b = await _register_and_get_token(client, "cand_d", ntrp="3.5")
    court = await _seed_court(session)

    pref_body = {
        "match_type": "singles",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
        "court_ids": [str(court.id)],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token_a), json=pref_body)
    await client.post("/api/v1/matching/preferences", headers=_auth(token_b), json=pref_body)

    # Block user B
    await client.post(f"/api/v1/blocks/{uid_b}", headers=_auth(token_a))

    resp = await client.get("/api/v1/matching/candidates", headers=_auth(token_a))
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_search_candidates_no_preference(client: AsyncClient, session: AsyncSession):
    """Should return 404 if user has no preference."""
    token, _ = await _register_and_get_token(client, "cand_e")

    resp = await client.get("/api/v1/matching/candidates", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_candidates_inactive(client: AsyncClient, session: AsyncSession):
    """Should return 400 if preference is inactive."""
    token, _ = await _register_and_get_token(client, "cand_f")

    pref_body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token), json=pref_body)
    await client.patch("/api/v1/matching/preferences/toggle", headers=_auth(token))

    resp = await client.get("/api/v1/matching/candidates", headers=_auth(token))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_booking_recommendations(client: AsyncClient, session: AsyncSession):
    """Should return open bookings matching user's preferences."""
    token_a, uid_a = await _register_and_get_token(client, "brec_a", ntrp="3.5")
    token_b, uid_b = await _register_and_get_token(client, "brec_b", ntrp="3.5")
    court = await _seed_court(session)

    # User A creates a preference
    pref_body = {
        "match_type": "singles",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
        "court_ids": [str(court.id)],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token_a), json=pref_body)

    # User B creates a booking on a Saturday (day_of_week=5)
    from datetime import date, timedelta
    # Find next Saturday
    today = date.today()
    days_until_sat = (5 - today.weekday()) % 7
    if days_until_sat == 0:
        days_until_sat = 7
    next_sat = today + timedelta(days=days_until_sat)

    await client.post(
        "/api/v1/bookings",
        headers=_auth(token_b),
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": next_sat.isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )

    resp = await client.get("/api/v1/matching/bookings", headers=_auth(token_a))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["creator_nickname"] == "Player_brec_b"
    assert data[0]["score"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_matching.py -v -k "candidates or booking_rec"`
Expected: FAIL — search functions not defined

- [ ] **Step 3: Add candidate search functions to `app/services/matching.py`**

```python
from datetime import timedelta
from app.models.block import Block
from app.models.booking import Booking, BookingStatus
from sqlalchemy import and_, or_


async def search_candidates(
    session: AsyncSession,
    user: User,
    pref: MatchPreference,
    *,
    limit: int = 10,
) -> list[dict]:
    """Find and rank compatible users for user-to-user matching (singles only)."""
    # Get all active preferences (excluding self, inactive, expired)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    result = await session.execute(
        select(MatchPreference)
        .options(
            selectinload(MatchPreference.time_slots),
            selectinload(MatchPreference.preferred_courts),
            selectinload(MatchPreference.user),
        )
        .where(
            MatchPreference.user_id != user.id,
            MatchPreference.is_active == True,  # noqa: E712
            MatchPreference.last_active_at >= thirty_days_ago,
        )
    )
    candidates_prefs = list(result.scalars().all())

    # Filter blocked users
    blocked_result = await session.execute(
        select(Block).where(
            or_(
                Block.blocker_id == user.id,
                Block.blocked_id == user.id,
            )
        )
    )
    blocked_pairs = blocked_result.scalars().all()
    blocked_ids = set()
    for b in blocked_pairs:
        blocked_ids.add(b.blocker_id)
        blocked_ids.add(b.blocked_id)
    blocked_ids.discard(user.id)

    scored = []
    for cp in candidates_prefs:
        candidate = cp.user
        if candidate.id in blocked_ids:
            continue
        if candidate.is_suspended:
            continue

        score = await compute_match_score(session, user, pref, candidate, cp)
        if score is not None:
            scored.append({
                "user_id": str(candidate.id),
                "nickname": candidate.nickname,
                "gender": candidate.gender.value,
                "ntrp_level": candidate.ntrp_level,
                "ntrp_label": candidate.ntrp_label,
                "credit_score": candidate.credit_score,
                "is_ideal_player": candidate.is_ideal_player,
                "city": candidate.city,
                "score": score,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


async def search_booking_recommendations(
    session: AsyncSession,
    user: User,
    pref: MatchPreference,
    *,
    limit: int = 10,
) -> list[dict]:
    """Find open bookings matching user's preferences."""
    from app.services.booking import _ntrp_to_float

    # Get open bookings not created by self
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.creator),
            selectinload(Booking.court),
        )
        .where(
            Booking.status == BookingStatus.OPEN,
            Booking.creator_id != user.id,
            Booking.play_date >= datetime.now(timezone.utc).date(),
        )
    )
    bookings = list(result.scalars().all())

    # Filter blocked
    blocked_result = await session.execute(
        select(Block).where(
            or_(
                Block.blocker_id == user.id,
                Block.blocked_id == user.id,
            )
        )
    )
    blocked_pairs = blocked_result.scalars().all()
    blocked_ids = set()
    for b in blocked_pairs:
        blocked_ids.add(b.blocker_id)
        blocked_ids.add(b.blocked_id)
    blocked_ids.discard(user.id)

    user_ntrp = _ntrp_to_float(user.ntrp_level)

    scored = []
    for booking in bookings:
        if booking.creator_id in blocked_ids:
            continue
        if booking.creator.is_suspended:
            continue

        # Gender hard filter
        from app.models.booking import GenderRequirement
        if booking.gender_requirement == GenderRequirement.MALE_ONLY and user.gender != Gender.MALE:
            continue
        if booking.gender_requirement == GenderRequirement.FEMALE_ONLY and user.gender != Gender.FEMALE:
            continue

        # NTRP hard filter
        booking_min = _ntrp_to_float(booking.min_ntrp)
        booking_max = _ntrp_to_float(booking.max_ntrp)
        if user_ntrp < booking_min - 0.05 or user_ntrp > booking_max + 0.05:
            continue

        # Time overlap: check if booking day/time overlaps with any user time slot
        booking_dow = booking.play_date.weekday()
        has_time_overlap = False
        for slot in pref.time_slots:
            if slot.day_of_week == booking_dow:
                overlap = _time_overlap_minutes(slot.start_time, slot.end_time, booking.start_time, booking.end_time)
                if overlap > 0:
                    has_time_overlap = True
                    break
        if not has_time_overlap:
            continue

        # Score the booking
        # NTRP: midpoint of booking range vs user's NTRP
        booking_mid = (booking_min + booking_max) / 2
        ntrp_gap = abs(user_ntrp - booking_mid)
        ntrp_score = 1.0 if ntrp_gap <= 0.5 else max(0.0, 1.0 - (ntrp_gap - 0.5))

        # Court match
        pref_court_ids = {pc.court_id for pc in pref.preferred_courts}
        court_score = 1.0 if booking.court_id in pref_court_ids else 0.3

        # Credit score of creator
        credit_score = booking.creator.credit_score / 100.0

        # Ideal player
        ideal_score = 1.0 if booking.creator.is_ideal_player else 0.0

        total = 35 * ntrp_score + 25 * 1.0 + 20 * court_score + 10 * credit_score + 5 * 1.0 + 5 * ideal_score
        total = round(total, 2)

        scored.append({
            "booking_id": str(booking.id),
            "creator_id": str(booking.creator_id),
            "creator_nickname": booking.creator.nickname,
            "court_id": str(booking.court_id),
            "court_name": booking.court.name,
            "match_type": booking.match_type.value,
            "play_date": booking.play_date.isoformat(),
            "start_time": booking.start_time.isoformat(),
            "end_time": booking.end_time.isoformat(),
            "min_ntrp": booking.min_ntrp,
            "max_ntrp": booking.max_ntrp,
            "gender_requirement": booking.gender_requirement.value,
            "score": total,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
```

- [ ] **Step 4: Add candidate search endpoints to `app/routers/matching.py`**

Add these imports at the top:

```python
from app.schemas.matching import CandidateResponse, BookingRecommendationResponse
from app.services.matching import search_candidates, search_booking_recommendations
```

Add these endpoints:

```python
@router.get("/candidates", response_model=list[CandidateResponse])
async def find_candidates(user: CurrentUser, session: DbSession, lang: Lang):
    pref = await get_preference_by_user(session, user.id)
    if pref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    if not pref.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("matching.preference_inactive", lang))

    candidates = await search_candidates(session, user, pref)
    return candidates


@router.get("/bookings", response_model=list[BookingRecommendationResponse])
async def find_booking_recommendations(user: CurrentUser, session: DbSession, lang: Lang):
    pref = await get_preference_by_user(session, user.id)
    if pref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    if not pref.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("matching.preference_inactive", lang))

    bookings = await search_booking_recommendations(session, user, pref)
    return bookings
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_matching.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/matching.py app/routers/matching.py tests/test_matching.py
git commit -m "feat: add candidate search and booking recommendation endpoints"
```

---

### Task 7: Match proposal service

**Files:**
- Create: `app/services/match_proposal.py`
- Modify: `tests/test_matching.py`

- [ ] **Step 1: Write failing tests for proposals**

Add to `tests/test_matching.py`:

```python
# --- Proposal Tests ---


@pytest.mark.asyncio
async def test_create_proposal(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "prop_a")
    token_b, uid_b = await _register_and_get_token(client, "prop_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token_a),
        json={
            "target_id": uid_b,
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "message": "Want to play?",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["proposer_id"] == uid_a
    assert data["target_id"] == uid_b
    assert data["message"] == "Want to play?"


@pytest.mark.asyncio
async def test_create_proposal_to_self(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "prop_c")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token),
        json={
            "target_id": uid,
            "court_id": str(court.id),
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_proposal_duplicate_pending(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "prop_d")
    token_b, uid_b = await _register_and_get_token(client, "prop_e")
    court = await _seed_court(session)

    body = {
        "target_id": uid_b,
        "court_id": str(court.id),
        "play_date": (date.today() + timedelta(days=7)).isoformat(),
        "start_time": "10:00:00",
        "end_time": "12:00:00",
    }
    resp1 = await client.post("/api/v1/matching/proposals", headers=_auth(token_a), json=body)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/matching/proposals", headers=_auth(token_a), json=body)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_proposal_blocked(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "prop_f")
    token_b, uid_b = await _register_and_get_token(client, "prop_g")
    court = await _seed_court(session)

    await client.post(f"/api/v1/blocks/{uid_b}", headers=_auth(token_a))

    resp = await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token_a),
        json={
            "target_id": uid_b,
            "court_id": str(court.id),
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_proposal_daily_cap(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "prop_cap")
    court = await _seed_court(session)

    # Create 5 proposals to 5 different users (daily cap)
    for i in range(5):
        t_b, uid_b = await _register_and_get_token(client, f"prop_cap_target_{i}")
        resp = await client.post(
            "/api/v1/matching/proposals",
            headers=_auth(token_a),
            json={
                "target_id": uid_b,
                "court_id": str(court.id),
                "play_date": (date.today() + timedelta(days=7)).isoformat(),
                "start_time": "10:00:00",
                "end_time": "12:00:00",
            },
        )
        assert resp.status_code == 201

    # 6th proposal should be rejected
    t_last, uid_last = await _register_and_get_token(client, "prop_cap_target_last")
    resp = await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token_a),
        json={
            "target_id": uid_last,
            "court_id": str(court.id),
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_accept_proposal_creates_booking(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "prop_acc_a")
    token_b, uid_b = await _register_and_get_token(client, "prop_acc_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token_a),
        json={
            "target_id": uid_b,
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
    )
    proposal_id = resp.json()["id"]

    # Target accepts
    resp = await client.patch(
        f"/api/v1/matching/proposals/{proposal_id}",
        headers=_auth(token_b),
        json={"status": "accepted"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    # Verify booking was created
    resp = await client.get("/api/v1/bookings/my", headers=_auth(token_a))
    assert resp.status_code == 200
    bookings = resp.json()
    assert len(bookings) >= 1
    assert bookings[0]["status"] == "open"


@pytest.mark.asyncio
async def test_reject_proposal(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "prop_rej_a")
    token_b, uid_b = await _register_and_get_token(client, "prop_rej_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token_a),
        json={
            "target_id": uid_b,
            "court_id": str(court.id),
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
    )
    proposal_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/matching/proposals/{proposal_id}",
        headers=_auth(token_b),
        json={"status": "rejected"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_respond_not_target(client: AsyncClient, session: AsyncSession):
    """Only the target can respond to a proposal."""
    token_a, uid_a = await _register_and_get_token(client, "prop_nt_a")
    token_b, uid_b = await _register_and_get_token(client, "prop_nt_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token_a),
        json={
            "target_id": uid_b,
            "court_id": str(court.id),
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
    )
    proposal_id = resp.json()["id"]

    # Proposer tries to accept their own proposal
    resp = await client.patch(
        f"/api/v1/matching/proposals/{proposal_id}",
        headers=_auth(token_a),
        json={"status": "accepted"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_proposals(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "prop_list_a")
    token_b, uid_b = await _register_and_get_token(client, "prop_list_b")
    court = await _seed_court(session)

    await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token_a),
        json={
            "target_id": uid_b,
            "court_id": str(court.id),
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
    )

    # Proposer sees it as sent
    resp = await client.get("/api/v1/matching/proposals?direction=sent", headers=_auth(token_a))
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Target sees it as received
    resp = await client.get("/api/v1/matching/proposals?direction=received", headers=_auth(token_b))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_matching.py -v -k "prop"`
Expected: FAIL — proposal endpoints not defined

- [ ] **Step 3: Create the match proposal service**

```python
# app/services/match_proposal.py
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.matching import MatchProposal, ProposalStatus
from app.models.notification import NotificationType
from app.models.user import User
from app.services.block import is_blocked
from app.services.booking import create_booking
from app.services.notification import create_notification
from app.services.user import get_user_by_id

DAILY_PROPOSAL_CAP = 5
PROPOSAL_EXPIRY_HOURS = 48


async def create_proposal(
    session: AsyncSession,
    *,
    proposer: User,
    target_id: uuid.UUID,
    court_id: uuid.UUID,
    match_type: str = "singles",
    play_date: date,
    start_time: time,
    end_time: time,
    message: str | None = None,
    lang: str = "en",
) -> MatchProposal:
    # Cannot propose to self
    if proposer.id == target_id:
        raise ValueError("cannot_propose_self")

    # Check target exists
    target = await get_user_by_id(session, target_id)
    if target is None:
        raise ValueError("target_not_found")

    # Check block
    if await is_blocked(session, proposer.id, target_id):
        raise ValueError("blocked")

    # Check duplicate pending
    existing = await session.execute(
        select(MatchProposal).where(
            MatchProposal.proposer_id == proposer.id,
            MatchProposal.target_id == target_id,
            MatchProposal.status == ProposalStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError("duplicate_pending")

    # Check daily cap
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count_result = await session.execute(
        select(func.count(MatchProposal.id)).where(
            MatchProposal.proposer_id == proposer.id,
            MatchProposal.created_at >= today_start,
        )
    )
    if count_result.scalar_one() >= DAILY_PROPOSAL_CAP:
        raise PermissionError("daily_cap")

    proposal = MatchProposal(
        proposer_id=proposer.id,
        target_id=target_id,
        court_id=court_id,
        match_type=match_type,
        play_date=play_date,
        start_time=start_time,
        end_time=end_time,
        message=message,
    )
    session.add(proposal)

    await create_notification(
        session,
        recipient_id=target_id,
        type=NotificationType.MATCH_PROPOSAL_RECEIVED,
        actor_id=proposer.id,
        target_type="match_proposal",
        target_id=proposal.id,
    )

    await session.commit()
    return await get_proposal_by_id(session, proposal.id)


async def get_proposal_by_id(
    session: AsyncSession, proposal_id: uuid.UUID
) -> MatchProposal | None:
    result = await session.execute(
        select(MatchProposal)
        .options(
            selectinload(MatchProposal.proposer),
            selectinload(MatchProposal.target),
            selectinload(MatchProposal.court),
        )
        .where(MatchProposal.id == proposal_id)
    )
    proposal = result.scalar_one_or_none()
    if proposal and proposal.status == ProposalStatus.PENDING:
        # Lazy expiry check
        expiry_time = proposal.created_at + timedelta(hours=PROPOSAL_EXPIRY_HOURS)
        if datetime.now(timezone.utc) > expiry_time:
            proposal.status = ProposalStatus.EXPIRED
            await session.commit()
            await session.refresh(proposal)
    return proposal


async def respond_to_proposal(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    responder: User,
    new_status: str,
    lang: str = "en",
) -> MatchProposal:
    proposal = await get_proposal_by_id(session, proposal_id)
    if proposal is None:
        raise ValueError("proposal_not_found")

    if proposal.target_id != responder.id:
        raise PermissionError("not_target")

    if proposal.status != ProposalStatus.PENDING:
        raise ValueError("proposal_not_pending")

    # Check proposer is not suspended (edge case: suspended after sending)
    proposer = await get_user_by_id(session, proposal.proposer_id)
    if proposer.is_suspended and new_status == "accepted":
        proposal.status = ProposalStatus.EXPIRED
        await session.commit()
        raise ValueError("proposer_suspended")

    proposal.status = ProposalStatus(new_status)
    proposal.responded_at = datetime.now(timezone.utc)

    if new_status == "accepted":
        # Auto-create booking
        await create_booking(
            session,
            creator=proposer,
            court_id=proposal.court_id,
            match_type=proposal.match_type,
            play_date=proposal.play_date,
            start_time=proposal.start_time,
            end_time=proposal.end_time,
            min_ntrp=proposer.ntrp_level,
            max_ntrp=responder.ntrp_level,
        )
        # The booking is created with proposer as creator.
        # Now we need to add the target as accepted participant.
        # create_booking already adds the creator, so we join + auto-accept the target.
        from app.services.booking import get_booking_by_id, join_booking, update_participant_status
        from app.models.booking import Booking, BookingStatus
        # Find the booking just created (latest by proposer)
        result = await session.execute(
            select(Booking)
            .where(
                Booking.creator_id == proposer.id,
                Booking.play_date == proposal.play_date,
                Booking.start_time == proposal.start_time,
                Booking.court_id == proposal.court_id,
                Booking.status == BookingStatus.OPEN,
            )
            .order_by(Booking.created_at.desc())
            .limit(1)
        )
        booking = result.scalar_one_or_none()
        if booking:
            from app.models.booking import BookingParticipant, ParticipantStatus
            participant = BookingParticipant(
                booking_id=booking.id,
                user_id=responder.id,
                status=ParticipantStatus.ACCEPTED,
            )
            session.add(participant)

        await create_notification(
            session,
            recipient_id=proposal.proposer_id,
            type=NotificationType.MATCH_PROPOSAL_ACCEPTED,
            actor_id=responder.id,
            target_type="match_proposal",
            target_id=proposal.id,
        )
    elif new_status == "rejected":
        await create_notification(
            session,
            recipient_id=proposal.proposer_id,
            type=NotificationType.MATCH_PROPOSAL_REJECTED,
            actor_id=responder.id,
            target_type="match_proposal",
            target_id=proposal.id,
        )

    await session.commit()
    return await get_proposal_by_id(session, proposal.id)


async def list_proposals(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    direction: str | None = None,
    status_filter: str | None = None,
) -> list[MatchProposal]:
    query = select(MatchProposal).options(
        selectinload(MatchProposal.proposer),
        selectinload(MatchProposal.target),
        selectinload(MatchProposal.court),
    )

    if direction == "sent":
        query = query.where(MatchProposal.proposer_id == user_id)
    elif direction == "received":
        query = query.where(MatchProposal.target_id == user_id)
    else:
        query = query.where(
            (MatchProposal.proposer_id == user_id) | (MatchProposal.target_id == user_id)
        )

    if status_filter:
        query = query.where(MatchProposal.status == ProposalStatus(status_filter))

    query = query.order_by(MatchProposal.created_at.desc())
    result = await session.execute(query)
    proposals = list(result.scalars().all())

    # Lazy expiry check for pending proposals
    now = datetime.now(timezone.utc)
    for p in proposals:
        if p.status == ProposalStatus.PENDING:
            expiry_time = p.created_at + timedelta(hours=PROPOSAL_EXPIRY_HOURS)
            if now > expiry_time:
                p.status = ProposalStatus.EXPIRED

    if any(p.status == ProposalStatus.EXPIRED for p in proposals):
        await session.commit()

    return proposals


async def expire_proposals_on_block(
    session: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> None:
    """Expire any pending proposals between two users when a block occurs."""
    result = await session.execute(
        select(MatchProposal).where(
            MatchProposal.status == ProposalStatus.PENDING,
            (
                (MatchProposal.proposer_id == user_a) & (MatchProposal.target_id == user_b)
                | (MatchProposal.proposer_id == user_b) & (MatchProposal.target_id == user_a)
            ),
        )
    )
    for proposal in result.scalars().all():
        proposal.status = ProposalStatus.EXPIRED
    await session.flush()
```

- [ ] **Step 4: Add proposal endpoints to `app/routers/matching.py`**

Add imports:

```python
from app.schemas.matching import ProposalCreateRequest, ProposalResponse, ProposalRespondRequest
from app.services.match_proposal import create_proposal, get_proposal_by_id, list_proposals, respond_to_proposal
```

Add helper:

```python
def _proposal_to_response(proposal) -> ProposalResponse:
    return ProposalResponse(
        id=proposal.id,
        proposer_id=proposal.proposer_id,
        proposer_nickname=proposal.proposer.nickname,
        target_id=proposal.target_id,
        target_nickname=proposal.target.nickname,
        court_id=proposal.court_id,
        court_name=proposal.court.name,
        match_type=proposal.match_type,
        play_date=proposal.play_date,
        start_time=proposal.start_time,
        end_time=proposal.end_time,
        message=proposal.message,
        status=proposal.status.value,
        created_at=proposal.created_at,
        responded_at=proposal.responded_at,
    )
```

Add endpoints:

```python
@router.post("/proposals", response_model=ProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_match_proposal(body: ProposalCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        proposal = await create_proposal(
            session,
            proposer=user,
            target_id=body.target_id,
            court_id=body.court_id,
            match_type=body.match_type,
            play_date=body.play_date,
            start_time=body.start_time,
            end_time=body.end_time,
            message=body.message,
            lang=lang,
        )
    except ValueError as e:
        msg = str(e)
        if msg == "cannot_propose_self":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("matching.cannot_propose_self", lang))
        if msg == "target_not_found":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("matching.target_not_found", lang))
        if msg == "blocked":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("block.user_blocked", lang))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("matching.duplicate_pending", lang))
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=t("matching.proposal_daily_cap", lang))
    return _proposal_to_response(proposal)


@router.get("/proposals", response_model=list[ProposalResponse])
async def get_proposals(
    user: CurrentUser,
    session: DbSession,
    direction: str | None = Query(default=None, pattern=r"^(sent|received)$"),
    proposal_status: str | None = Query(default=None, alias="status", pattern=r"^(pending|accepted|rejected|expired)$"),
):
    proposals = await list_proposals(session, user.id, direction=direction, status_filter=proposal_status)
    return [_proposal_to_response(p) for p in proposals]


@router.patch("/proposals/{proposal_id}", response_model=ProposalResponse)
async def respond_to_match_proposal(
    proposal_id: str, body: ProposalRespondRequest, user: CurrentUser, session: DbSession, lang: Lang
):
    try:
        proposal = await respond_to_proposal(
            session,
            proposal_id=uuid.UUID(proposal_id),
            responder=user,
            new_status=body.status,
            lang=lang,
        )
    except ValueError as e:
        msg = str(e)
        if msg == "proposal_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.proposal_not_found", lang))
        if msg == "proposal_not_pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("matching.proposal_not_pending", lang))
        if msg == "proposer_suspended":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("matching.proposer_suspended", lang))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("matching.proposal_not_target", lang))
    return _proposal_to_response(proposal)
```

Add `import uuid` to the imports if not already present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_matching.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/match_proposal.py app/routers/matching.py tests/test_matching.py
git commit -m "feat: add match proposal service with auto-booking on accept"
```

---

### Task 8: Passive matching (event-triggered notifications)

**Files:**
- Modify: `app/services/matching.py`
- Modify: `tests/test_matching.py`

- [ ] **Step 1: Write failing test for passive matching**

Add to `tests/test_matching.py`:

```python
from app.models.notification import Notification, NotificationType


@pytest.mark.asyncio
async def test_passive_match_on_create(client: AsyncClient, session: AsyncSession):
    """Creating a preference should trigger MATCH_SUGGESTION notifications for good matches."""
    token_a, uid_a = await _register_and_get_token(client, "passive_a", ntrp="3.5")
    court = await _seed_court(session)

    # User A creates preference first
    pref_body = {
        "match_type": "singles",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
        "court_ids": [str(court.id)],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token_a), json=pref_body)

    # User B creates a matching preference — this should trigger notifications
    token_b, uid_b = await _register_and_get_token(client, "passive_b", ntrp="3.5")
    await client.post("/api/v1/matching/preferences", headers=_auth(token_b), json=pref_body)

    # Check that user A received a MATCH_SUGGESTION notification
    result = await session.execute(
        select(Notification).where(
            Notification.recipient_id == uuid.UUID(uid_a),
            Notification.type == NotificationType.MATCH_SUGGESTION,
        )
    )
    notifications = result.scalars().all()
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_passive_match_on_reactivate(client: AsyncClient, session: AsyncSession):
    """Reactivating a preference should trigger passive matching."""
    token_a, uid_a = await _register_and_get_token(client, "passive_c", ntrp="3.5")
    token_b, uid_b = await _register_and_get_token(client, "passive_d", ntrp="3.5")
    court = await _seed_court(session)

    pref_body = {
        "match_type": "singles",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
        "court_ids": [str(court.id)],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token_a), json=pref_body)
    await client.post("/api/v1/matching/preferences", headers=_auth(token_b), json=pref_body)

    # Toggle off then on
    await client.patch("/api/v1/matching/preferences/toggle", headers=_auth(token_b))
    await client.patch("/api/v1/matching/preferences/toggle", headers=_auth(token_b))

    # Check notifications (should have 2: one from initial create, one from reactivate)
    result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == uuid.UUID(uid_a),
            Notification.type == NotificationType.MATCH_SUGGESTION,
        )
    )
    count = result.scalar_one()
    assert count >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_matching.py -v -k "passive"`
Expected: FAIL — no suggestions created yet

- [ ] **Step 3: Add passive matching function to `app/services/matching.py`**

```python
from app.models.notification import Notification, NotificationType
from app.services.notification import create_notification

SUGGESTION_SCORE_THRESHOLD = 60
SUGGESTION_MAX_PER_EVENT = 3
SUGGESTION_COOLDOWN_DAYS = 7


async def trigger_passive_matching(
    session: AsyncSession, user: User, pref: MatchPreference
) -> None:
    """Find top matches and send MATCH_SUGGESTION notifications."""
    candidates = await search_candidates(session, user, pref, limit=SUGGESTION_MAX_PER_EVENT)

    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=SUGGESTION_COOLDOWN_DAYS)

    for candidate in candidates:
        if candidate["score"] < SUGGESTION_SCORE_THRESHOLD:
            continue

        candidate_id = uuid.UUID(candidate["user_id"])

        # Check cooldown: don't re-suggest if notification sent within 7 days
        existing = await session.execute(
            select(Notification.id).where(
                Notification.type == NotificationType.MATCH_SUGGESTION,
                Notification.recipient_id == candidate_id,
                Notification.actor_id == user.id,
                Notification.created_at >= cooldown_cutoff,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        # Check no pending/rejected proposal between them
        from app.models.matching import MatchProposal, ProposalStatus
        existing_proposal = await session.execute(
            select(MatchProposal.id).where(
                MatchProposal.status.in_([ProposalStatus.PENDING, ProposalStatus.REJECTED]),
                (
                    (MatchProposal.proposer_id == user.id) & (MatchProposal.target_id == candidate_id)
                    | (MatchProposal.proposer_id == candidate_id) & (MatchProposal.target_id == user.id)
                ),
            )
        )
        if existing_proposal.scalar_one_or_none() is not None:
            continue

        # Notify the candidate about the current user
        await create_notification(
            session,
            recipient_id=candidate_id,
            type=NotificationType.MATCH_SUGGESTION,
            actor_id=user.id,
            target_type="match_preference",
            target_id=pref.id,
        )

        # Also notify the current user about the candidate
        await create_notification(
            session,
            recipient_id=user.id,
            type=NotificationType.MATCH_SUGGESTION,
            actor_id=candidate_id,
            target_type="match_preference",
            target_id=pref.id,
        )

    await session.flush()
```

- [ ] **Step 4: Wire passive matching into preference CRUD**

In `app/services/matching.py`, update `create_preference` to call `trigger_passive_matching` after commit:

At the end of `create_preference`, before the return, add:

```python
    pref = await get_preference_by_user(session, user_id)
    # Trigger passive matching
    user = await session.get(User, user_id)
    await trigger_passive_matching(session, user, pref)
    await session.commit()
    return pref
```

Update `update_preference` similarly — at the end, before return:

```python
    pref = await get_preference_by_user(session, user_id)
    user = await session.get(User, user_id)
    await trigger_passive_matching(session, user, pref)
    await session.commit()
    return pref
```

Update `toggle_preference` — after setting `is_active = True`, trigger passive matching:

```python
    pref.is_active = not pref.is_active
    if pref.is_active:
        pref.last_active_at = datetime.now(timezone.utc)
    await session.commit()
    pref = await get_preference_by_user(session, user_id)
    if pref.is_active:
        user = await session.get(User, user_id)
        await trigger_passive_matching(session, user, pref)
        await session.commit()
    return pref
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_matching.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/matching.py tests/test_matching.py
git commit -m "feat: add passive matching with event-triggered notifications"
```

---

### Task 9: Block integration for proposals

**Files:**
- Modify: `app/services/block.py`
- Modify: `tests/test_matching.py`

- [ ] **Step 1: Write failing test for block-expires-proposals**

Add to `tests/test_matching.py`:

```python
@pytest.mark.asyncio
async def test_block_expires_pending_proposals(client: AsyncClient, session: AsyncSession):
    """Blocking a user should expire pending proposals between them."""
    token_a, uid_a = await _register_and_get_token(client, "blk_prop_a")
    token_b, uid_b = await _register_and_get_token(client, "blk_prop_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/matching/proposals",
        headers=_auth(token_a),
        json={
            "target_id": uid_b,
            "court_id": str(court.id),
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
    )
    proposal_id = resp.json()["id"]

    # Block user B
    await client.post(f"/api/v1/blocks/{uid_b}", headers=_auth(token_a))

    # Check proposal is now expired
    from app.models.matching import MatchProposal
    result = await session.execute(
        select(MatchProposal).where(MatchProposal.id == uuid.UUID(proposal_id))
    )
    proposal = result.scalar_one()
    assert proposal.status.value == "expired"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_matching.py::test_block_expires_pending_proposals -v`
Expected: FAIL — proposals not expired on block

- [ ] **Step 3: Add `expire_proposals_on_block` call to `app/services/block.py`**

In `create_block`, after `await remove_follows_between(...)` and before the review-hiding loop, add:

```python
    from app.services.match_proposal import expire_proposals_on_block
    await expire_proposals_on_block(session, blocker_id, blocked_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_matching.py::test_block_expires_pending_proposals -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check nothing is broken**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/block.py tests/test_matching.py
git commit -m "feat: expire pending proposals on block creation"
```

---

### Task 10: Update CLAUDE.md with matching documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add matching system documentation to CLAUDE.md**

In the "Key patterns" section, after the "Ideal player" bullet, add:

```markdown
- **Smart Matching**: `services/matching.py` + `services/match_proposal.py` + `routers/matching.py` — two-mode matching system. User-to-user: scored pairing (singles only) with proposal → accept → auto-create-booking flow. User-to-booking: recommends open bookings matching preferences. Scoring: NTRP proximity (35), time overlap (25), court proximity (20), credit (10), gender (5), ideal player (5). Hard filters: blocked, gender mismatch, NTRP gap > 1.5, no time overlap. `MatchPreference` stores weekly recurring time slots (half-hour granularity) + preferred courts. `MatchProposal` lifecycle: pending → accepted/rejected/expired (48h lazy expiry). Daily proposal cap: 5 per user. Passive matching: `trigger_passive_matching()` fires on preference create/update/reactivate, sends `MATCH_SUGGESTION` notifications to top 3 matches with score >= 60 and 7-day cooldown. Auto-expire: preferences with `last_active_at` > 30 days excluded from search.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with smart matching system details"
```
