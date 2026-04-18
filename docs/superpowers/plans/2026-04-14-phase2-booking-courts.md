# Phase 2: Booking System + Courts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the court management and booking (约球) system — users can browse courts, post match requests, join/confirm/cancel/complete bookings, with automatic credit score integration.

**Architecture:** Follows Phase 1 patterns — new models in `app/models/`, Pydantic schemas in `app/schemas/`, business logic in `app/services/`, FastAPI routers in `app/routers/`. Booking cancellation calculates credit penalty tier automatically from play datetime. Courts are hybrid: admin-seeded + user-submitted (unapproved until reviewed).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL, Pydantic v2, pytest, httpx

**Spec Reference:** `docs/superpowers/specs/2026-04-14-phase2-booking-courts.md`

---

## File Structure

```
app/
├── models/
│   ├── __init__.py              # Modify: add Court, Booking, BookingParticipant imports
│   ├── court.py                 # Create: Court model + CourtType, SurfaceType enums
│   └── booking.py               # Create: Booking, BookingParticipant models + enums
├── schemas/
│   ├── court.py                 # Create: Court request/response schemas
│   └── booking.py               # Create: Booking request/response schemas
├── services/
│   ├── court.py                 # Create: Court CRUD
│   └── booking.py               # Create: Booking business logic
├── routers/
│   ├── courts.py                # Create: Court endpoints
│   └── bookings.py              # Create: Booking endpoints
├── main.py                      # Modify: register courts + bookings routers
├── i18n.py                      # Modify: add booking/court i18n keys
tests/
├── conftest.py                  # Modify: import new models for table creation
├── test_courts.py               # Create: Court tests
└── test_bookings.py             # Create: Booking lifecycle tests
alembic/
└── versions/
    └── xxxx_add_courts_bookings.py  # Auto-generated migration
```

---

### Task 1: Court Model

**Files:**

- Create: `app/models/court.py`

- [ ] **Step 1: Create app/models/court.py**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CourtType(str, enum.Enum):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"


class SurfaceType(str, enum.Enum):
    HARD = "hard"
    CLAY = "clay"
    GRASS = "grass"


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(50))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    court_type: Mapped[CourtType] = mapped_column(Enum(CourtType))
    surface_type: Mapped[SurfaceType | None] = mapped_column(Enum(SurfaceType))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/xue/APP && uv run python -c "from app.models.court import Court, CourtType, SurfaceType; print('Court model OK')"`
Expected: `Court model OK`

- [ ] **Step 3: Commit**

```bash
git add app/models/court.py
git commit -m "feat: Court model with CourtType and SurfaceType enums"
```

---

### Task 2: Booking + BookingParticipant Models

**Files:**

- Create: `app/models/booking.py`

- [ ] **Step 1: Create app/models/booking.py**

```python
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
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/xue/APP && uv run python -c "from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus, MatchType, GenderRequirement; print('Booking models OK')"`
Expected: `Booking models OK`

- [ ] **Step 3: Commit**

```bash
git add app/models/booking.py
git commit -m "feat: Booking and BookingParticipant models with status enums"
```

---

### Task 3: Update Models Init + Conftest + Migration

**Files:**

- Modify: `app/models/__init__.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update app/models/**init**.py**

Replace the entire content with:

```python
from app.models.user import User, UserAuth
from app.models.credit import CreditLog
from app.models.court import Court
from app.models.booking import Booking, BookingParticipant

__all__ = ["User", "UserAuth", "CreditLog", "Court", "Booking", "BookingParticipant"]
```

- [ ] **Step 2: Update tests/conftest.py imports**

In `tests/conftest.py`, change the models import line from:

```python
from app.models import CreditLog, User, UserAuth  # noqa: F401
```

to:

```python
from app.models import Booking, BookingParticipant, Court, CreditLog, User, UserAuth  # noqa: F401
```

- [ ] **Step 3: Generate Alembic migration**

Run: `cd /Users/xue/APP && uv run alembic revision --autogenerate -m "add courts, bookings, booking_participants tables"`

- [ ] **Step 4: Review the generated migration**

Open and review the file in `alembic/versions/`. Verify it creates:

- `courts` table with all columns
- `bookings` table with all columns and foreign keys to `users` and `courts`
- `booking_participants` table with unique constraint on `(booking_id, user_id)`

- [ ] **Step 5: Run the migration**

Run: `cd /Users/xue/APP && uv run alembic upgrade head`
Expected: Migration runs successfully, tables created.

- [ ] **Step 6: Verify tables exist**

```bash
psql lets_tennis -c "\dt"
```

Expected: `courts`, `bookings`, `booking_participants` tables listed alongside existing tables.

- [ ] **Step 7: Run existing tests to ensure nothing broke**

Run: `cd /Users/xue/APP && uv run pytest tests/ -v`
Expected: All existing tests still PASS.

- [ ] **Step 8: Commit**

```bash
git add app/models/__init__.py tests/conftest.py alembic/
git commit -m "feat: Alembic migration for courts, bookings, booking_participants tables"
```

---

### Task 4: i18n — Add Booking & Court Translation Keys

**Files:**

- Modify: `app/i18n.py`

- [ ] **Step 1: Add new translation keys to app/i18n.py**

Add the following entries to the `_MESSAGES` dict in `app/i18n.py`, after the existing `"common.forbidden"` entry:

```python
    "booking.not_found": {
        "zh-Hans": "约球未找到",
        "zh-Hant": "約球未找到",
        "en": "Booking not found",
    },
    "booking.not_open": {
        "zh-Hans": "该约球不在开放状态",
        "zh-Hant": "該約球不在開放狀態",
        "en": "Booking is not open for joining",
    },
    "booking.already_joined": {
        "zh-Hans": "你已经加入了这个约球",
        "zh-Hant": "你已經加入了這個約球",
        "en": "You have already joined this booking",
    },
    "booking.full": {
        "zh-Hans": "约球人数已满",
        "zh-Hant": "約球人數已滿",
        "en": "Booking is full",
    },
    "booking.ntrp_out_of_range": {
        "zh-Hans": "你的水平不在要求范围内",
        "zh-Hant": "你的水平不在要求範圍內",
        "en": "Your NTRP level is outside the required range",
    },
    "booking.gender_mismatch": {
        "zh-Hans": "该约球有性别要求",
        "zh-Hant": "該約球有性別要求",
        "en": "This booking has a gender requirement you don't meet",
    },
    "booking.credit_too_low": {
        "zh-Hans": "信誉积分不足，无法发起约球",
        "zh-Hant": "信誉积分不足，無法發起約球",
        "en": "Credit score too low to create a booking",
    },
    "booking.not_creator": {
        "zh-Hans": "只有发起人才能执行此操作",
        "zh-Hant": "只有發起人才能執行此操作",
        "en": "Only the booking creator can perform this action",
    },
    "booking.not_enough_participants": {
        "zh-Hans": "参与人数不足，无法确认",
        "zh-Hant": "參與人數不足，無法確認",
        "en": "Not enough participants to confirm",
    },
    "booking.cannot_complete": {
        "zh-Hans": "约球尚未到达可完成状态",
        "zh-Hant": "約球尚未到達可完成狀態",
        "en": "Booking cannot be completed yet",
    },
    "booking.already_cancelled": {
        "zh-Hans": "约球已被取消",
        "zh-Hant": "約球已被取消",
        "en": "Booking has already been cancelled",
    },
    "booking.play_date_past": {
        "zh-Hans": "打球日期必须在未来",
        "zh-Hant": "打球日期必須在未來",
        "en": "Play date must be in the future",
    },
    "court.not_found": {
        "zh-Hans": "球场未找到",
        "zh-Hant": "球場未找到",
        "en": "Court not found",
    },
    "court.not_approved": {
        "zh-Hans": "球场尚未审核通过",
        "zh-Hant": "球場尚未審核通過",
        "en": "Court is not yet approved",
    },
```

- [ ] **Step 2: Verify translations work**

Run: `cd /Users/xue/APP && uv run python -c "from app.i18n import t; print(t('booking.not_found', 'zh-Hant')); print(t('court.not_found', 'en'))"`
Expected:

```
約球未找到
Court not found
```

- [ ] **Step 3: Commit**

```bash
git add app/i18n.py
git commit -m "feat: i18n translations for booking and court error messages"
```

---

### Task 5: Court Schemas

**Files:**

- Create: `app/schemas/court.py`

- [ ] **Step 1: Create app/schemas/court.py**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CourtCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    address: str = Field(..., min_length=1, max_length=255)
    city: str = Field(..., min_length=1, max_length=50)
    latitude: float | None = None
    longitude: float | None = None
    court_type: str = Field(..., pattern=r"^(indoor|outdoor)$")
    surface_type: str | None = Field(default=None, pattern=r"^(hard|clay|grass)$")


class CourtResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    city: str
    latitude: float | None
    longitude: float | None
    court_type: str
    surface_type: str | None
    is_approved: bool
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/xue/APP && uv run python -c "from app.schemas.court import CourtCreateRequest, CourtResponse; print('Court schemas OK')"`
Expected: `Court schemas OK`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/court.py
git commit -m "feat: Pydantic schemas for court endpoints"
```

---

### Task 6: Booking Schemas

**Files:**

- Create: `app/schemas/booking.py`

- [ ] **Step 1: Create app/schemas/booking.py**

```python
import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


class BookingCreateRequest(BaseModel):
    court_id: uuid.UUID
    match_type: str = Field(..., pattern=r"^(singles|doubles)$")
    play_date: date
    start_time: time
    end_time: time
    min_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    max_ntrp: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    gender_requirement: str = Field(default="any", pattern=r"^(male_only|female_only|any)$")
    cost_per_person: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)


class ParticipantResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    nickname: str
    status: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class BookingResponse(BaseModel):
    id: uuid.UUID
    creator_id: uuid.UUID
    court_id: uuid.UUID
    match_type: str
    play_date: date
    start_time: time
    end_time: time
    min_ntrp: str
    max_ntrp: str
    gender_requirement: str
    max_participants: int
    cost_per_person: int | None
    description: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingDetailResponse(BookingResponse):
    participants: list[ParticipantResponse]
    court_name: str


class ParticipantUpdateRequest(BaseModel):
    status: str = Field(..., pattern=r"^(accepted|rejected)$")
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/xue/APP && uv run python -c "from app.schemas.booking import BookingCreateRequest, BookingResponse, BookingDetailResponse, ParticipantUpdateRequest, ParticipantResponse; print('Booking schemas OK')"`
Expected: `Booking schemas OK`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/booking.py
git commit -m "feat: Pydantic schemas for booking endpoints"
```

---

### Task 7: Court Service

**Files:**

- Create: `app/services/court.py`

- [ ] **Step 1: Create app/services/court.py**

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType, SurfaceType


async def create_court(
    session: AsyncSession,
    *,
    name: str,
    address: str,
    city: str,
    court_type: str,
    latitude: float | None = None,
    longitude: float | None = None,
    surface_type: str | None = None,
    created_by: uuid.UUID | None = None,
    is_approved: bool = True,
) -> Court:
    court = Court(
        name=name,
        address=address,
        city=city,
        latitude=latitude,
        longitude=longitude,
        court_type=CourtType(court_type),
        surface_type=SurfaceType(surface_type) if surface_type else None,
        created_by=created_by,
        is_approved=is_approved,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def get_court_by_id(session: AsyncSession, court_id: uuid.UUID) -> Court | None:
    result = await session.execute(select(Court).where(Court.id == court_id))
    return result.scalar_one_or_none()


async def list_courts(
    session: AsyncSession,
    *,
    city: str | None = None,
    court_type: str | None = None,
    approved_only: bool = True,
) -> list[Court]:
    query = select(Court)
    if approved_only:
        query = query.where(Court.is_approved == True)
    if city:
        query = query.where(Court.city == city)
    if court_type:
        query = query.where(Court.court_type == CourtType(court_type))
    query = query.order_by(Court.name)
    result = await session.execute(query)
    return list(result.scalars().all())
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/xue/APP && uv run python -c "from app.services.court import create_court, get_court_by_id, list_courts; print('Court service OK')"`
Expected: `Court service OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/court.py
git commit -m "feat: court service with CRUD operations"
```

---

### Task 8: Court Router + Tests

**Files:**

- Create: `app/routers/courts.py`
- Create: `tests/test_courts.py`

- [ ] **Step 1: Create app/routers/courts.py**

```python
from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.court import CourtCreateRequest, CourtResponse
from app.services.court import create_court, get_court_by_id, list_courts

router = APIRouter()


@router.get("", response_model=list[CourtResponse])
async def get_courts(
    session: DbSession,
    city: str | None = Query(default=None),
    court_type: str | None = Query(default=None, pattern=r"^(indoor|outdoor)$"),
):
    courts = await list_courts(session, city=city, court_type=court_type)
    return courts


@router.get("/{court_id}", response_model=CourtResponse)
async def get_court(court_id: str, session: DbSession, lang: Lang):
    import uuid
    court = await get_court_by_id(session, uuid.UUID(court_id))
    if court is None or not court.is_approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("court.not_found", lang))
    return court


@router.post("", response_model=CourtResponse, status_code=status.HTTP_201_CREATED)
async def submit_court(body: CourtCreateRequest, user: CurrentUser, session: DbSession):
    court = await create_court(
        session,
        name=body.name,
        address=body.address,
        city=body.city,
        latitude=body.latitude,
        longitude=body.longitude,
        court_type=body.court_type,
        surface_type=body.surface_type,
        created_by=user.id,
        is_approved=False,
    )
    return court
```

- [ ] **Step 2: Write tests**

Create `tests/test_courts.py`:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType


async def _register_and_get_token(client: AsyncClient, username: str = "courtuser") -> str:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "CourtTest",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    return resp.json()["access_token"]


async def _seed_approved_court(session: AsyncSession, name: str = "Victoria Park Tennis", city: str = "Hong Kong") -> Court:
    court = Court(
        name=name,
        address="1 Hing Fat St, Causeway Bay",
        city=city,
        latitude=22.282,
        longitude=114.188,
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


@pytest.mark.asyncio
async def test_list_courts_empty(client: AsyncClient):
    resp = await client.get("/api/v1/courts")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_courts_with_seeded(client: AsyncClient, session: AsyncSession):
    await _seed_approved_court(session)
    resp = await client.get("/api/v1/courts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Victoria Park Tennis"
    assert data[0]["is_approved"] is True


@pytest.mark.asyncio
async def test_list_courts_filter_by_city(client: AsyncClient, session: AsyncSession):
    await _seed_approved_court(session, name="HK Court", city="Hong Kong")
    await _seed_approved_court(session, name="BJ Court", city="Beijing")
    resp = await client.get("/api/v1/courts", params={"city": "Hong Kong"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "HK Court"


@pytest.mark.asyncio
async def test_list_courts_excludes_unapproved(client: AsyncClient, session: AsyncSession):
    await _seed_approved_court(session)
    unapproved = Court(
        name="User Court",
        address="Some address",
        city="Hong Kong",
        court_type=CourtType.INDOOR,
        is_approved=False,
    )
    session.add(unapproved)
    await session.commit()

    resp = await client.get("/api/v1/courts")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Victoria Park Tennis"


@pytest.mark.asyncio
async def test_get_court_by_id(client: AsyncClient, session: AsyncSession):
    court = await _seed_approved_court(session)
    resp = await client.get(f"/api/v1/courts/{court.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Victoria Park Tennis"


@pytest.mark.asyncio
async def test_get_court_unapproved_returns_404(client: AsyncClient, session: AsyncSession):
    court = Court(
        name="Unapproved",
        address="Addr",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=False,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)

    resp = await client.get(f"/api/v1/courts/{court.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_court_by_user(client: AsyncClient):
    token = await _register_and_get_token(client)
    resp = await client.post(
        "/api/v1/courts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "My Local Court",
            "address": "123 Tennis Lane",
            "city": "Hong Kong",
            "court_type": "outdoor",
            "surface_type": "hard",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Local Court"
    assert data["is_approved"] is False


@pytest.mark.asyncio
async def test_submit_court_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/courts",
        json={
            "name": "No Auth Court",
            "address": "456 Fake St",
            "city": "Hong Kong",
            "court_type": "indoor",
        },
    )
    assert resp.status_code == 422
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/xue/APP && uv run pytest tests/test_courts.py -v`
Expected: All 8 tests PASS

- [ ] **Step 4: Commit**

```bash
git add app/routers/courts.py tests/test_courts.py
git commit -m "feat: court router with list, get, submit endpoints and tests"
```

---

### Task 9: Booking Service

**Files:**

- Create: `app/services/booking.py`

- [ ] **Step 1: Create app/services/booking.py**

```python
import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import (
    Booking,
    BookingParticipant,
    BookingStatus,
    GenderRequirement,
    MatchType,
    ParticipantStatus,
)
from app.models.court import Court
from app.models.credit import CreditReason
from app.models.user import Gender, User
from app.services.credit import apply_credit_change


def _ntrp_to_float(level: str) -> float:
    """Convert NTRP string like '3.5', '3.5+', '4.0-' to a float for comparison."""
    base = level.rstrip("+-")
    value = float(base)
    if level.endswith("+"):
        value += 0.05
    elif level.endswith("-"):
        value -= 0.05
    return value


def _get_cancel_reason(play_datetime: datetime) -> CreditReason:
    """Determine credit penalty tier based on time remaining until play."""
    now = datetime.now(timezone.utc)
    hours_until_play = (play_datetime - now).total_seconds() / 3600

    if hours_until_play >= 24:
        return CreditReason.CANCEL_24H
    elif hours_until_play >= 12:
        return CreditReason.CANCEL_12_24H
    else:
        return CreditReason.CANCEL_2H


async def create_booking(
    session: AsyncSession,
    *,
    creator: User,
    court_id: uuid.UUID,
    match_type: str,
    play_date: date,
    start_time: time,
    end_time: time,
    min_ntrp: str,
    max_ntrp: str,
    gender_requirement: str = "any",
    cost_per_person: int | None = None,
    description: str | None = None,
) -> Booking:
    max_participants = 2 if match_type == "singles" else 4

    booking = Booking(
        creator_id=creator.id,
        court_id=court_id,
        match_type=MatchType(match_type),
        play_date=play_date,
        start_time=start_time,
        end_time=end_time,
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_requirement=GenderRequirement(gender_requirement),
        max_participants=max_participants,
        cost_per_person=cost_per_person,
        description=description,
    )
    session.add(booking)
    await session.flush()

    participant = BookingParticipant(
        booking_id=booking.id,
        user_id=creator.id,
        status=ParticipantStatus.ACCEPTED,
    )
    session.add(participant)
    await session.commit()
    await session.refresh(booking)
    return booking


async def get_booking_by_id(session: AsyncSession, booking_id: uuid.UUID) -> Booking | None:
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.participants).selectinload(BookingParticipant.user),
            selectinload(Booking.court),
        )
        .where(Booking.id == booking_id)
    )
    return result.scalar_one_or_none()


async def list_bookings(
    session: AsyncSession,
    *,
    city: str | None = None,
    match_type: str | None = None,
    gender_requirement: str | None = None,
) -> list[Booking]:
    query = (
        select(Booking)
        .join(Booking.court)
        .where(Booking.status == BookingStatus.OPEN)
    )
    if city:
        query = query.where(Court.city == city)
    if match_type:
        query = query.where(Booking.match_type == MatchType(match_type))
    if gender_requirement:
        query = query.where(Booking.gender_requirement == GenderRequirement(gender_requirement))
    query = query.order_by(Booking.play_date, Booking.start_time)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_my_bookings(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
) -> list[Booking]:
    query = (
        select(Booking)
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(BookingParticipant.user_id == user_id)
    )
    if status:
        query = query.where(Booking.status == BookingStatus(status))
    query = query.order_by(Booking.play_date.desc(), Booking.start_time.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def join_booking(session: AsyncSession, booking: Booking, user: User) -> BookingParticipant:
    participant = BookingParticipant(
        booking_id=booking.id,
        user_id=user.id,
        status=ParticipantStatus.PENDING,
    )
    session.add(participant)
    await session.commit()
    await session.refresh(participant)
    return participant


def count_accepted_participants(booking: Booking) -> int:
    return sum(1 for p in booking.participants if p.status == ParticipantStatus.ACCEPTED)


async def confirm_booking(session: AsyncSession, booking: Booking) -> Booking:
    booking.status = BookingStatus.CONFIRMED
    await session.commit()
    await session.refresh(booking)
    return booking


async def cancel_booking(session: AsyncSession, booking: Booking, user: User) -> Booking:
    """Cancel a booking. If user is creator, cancels the whole booking. Otherwise cancels their participation."""
    play_dt = datetime.combine(booking.play_date, booking.start_time, tzinfo=timezone.utc)
    cancel_reason = _get_cancel_reason(play_dt)

    if user.id == booking.creator_id:
        booking.status = BookingStatus.CANCELLED
        await apply_credit_change(session, user, cancel_reason, description=f"Cancelled booking {booking.id}")
    else:
        for p in booking.participants:
            if p.user_id == user.id and p.status in (ParticipantStatus.PENDING, ParticipantStatus.ACCEPTED):
                p.status = ParticipantStatus.CANCELLED
                break
        await apply_credit_change(session, user, cancel_reason, description=f"Withdrew from booking {booking.id}")

    await session.commit()
    await session.refresh(booking)
    return booking


async def complete_booking(session: AsyncSession, booking: Booking) -> Booking:
    """Mark booking as completed and award credit to all accepted participants."""
    booking.status = BookingStatus.COMPLETED
    await session.flush()

    for p in booking.participants:
        if p.status == ParticipantStatus.ACCEPTED:
            user = p.user
            await apply_credit_change(session, user, CreditReason.ATTENDED, description=f"Attended booking {booking.id}")

    await session.commit()
    await session.refresh(booking)
    return booking


async def update_participant_status(
    session: AsyncSession, booking: Booking, user_id: uuid.UUID, new_status: str
) -> BookingParticipant | None:
    for p in booking.participants:
        if p.user_id == user_id:
            p.status = ParticipantStatus(new_status)
            await session.commit()
            await session.refresh(p)
            return p
    return None
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/xue/APP && uv run python -c "from app.services.booking import create_booking, get_booking_by_id, list_bookings, join_booking, cancel_booking, complete_booking, confirm_booking, update_participant_status, list_my_bookings; print('Booking service OK')"`
Expected: `Booking service OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/booking.py
git commit -m "feat: booking service with create, join, cancel, complete, confirm logic"
```

---

### Task 10: Booking Router

**Files:**

- Create: `app/routers/bookings.py`

- [ ] **Step 1: Create app/routers/bookings.py**

```python
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.models.booking import BookingStatus, ParticipantStatus
from app.models.user import Gender
from app.schemas.booking import (
    BookingCreateRequest,
    BookingDetailResponse,
    BookingResponse,
    ParticipantResponse,
    ParticipantUpdateRequest,
)
from app.services.booking import (
    cancel_booking,
    complete_booking,
    confirm_booking,
    count_accepted_participants,
    create_booking,
    get_booking_by_id,
    join_booking,
    list_bookings,
    list_my_bookings,
    update_participant_status,
    _ntrp_to_float,
)
from app.services.court import get_court_by_id

router = APIRouter()


def _booking_to_detail(booking) -> dict:
    """Convert a Booking ORM object to BookingDetailResponse-compatible dict."""
    participants = [
        ParticipantResponse(
            id=p.id,
            user_id=p.user_id,
            nickname=p.user.nickname,
            status=p.status.value,
            joined_at=p.joined_at,
        )
        for p in booking.participants
    ]
    return BookingDetailResponse(
        id=booking.id,
        creator_id=booking.creator_id,
        court_id=booking.court_id,
        match_type=booking.match_type.value,
        play_date=booking.play_date,
        start_time=booking.start_time,
        end_time=booking.end_time,
        min_ntrp=booking.min_ntrp,
        max_ntrp=booking.max_ntrp,
        gender_requirement=booking.gender_requirement.value,
        max_participants=booking.max_participants,
        cost_per_person=booking.cost_per_person,
        description=booking.description,
        status=booking.status.value,
        created_at=booking.created_at,
        participants=participants,
        court_name=booking.court.name,
    )


@router.post("", response_model=BookingDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_new_booking(body: BookingCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    if user.credit_score < 60:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.credit_too_low", lang))

    court = await get_court_by_id(session, body.court_id)
    if court is None or not court.is_approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("court.not_found", lang))

    if body.play_date < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.play_date_past", lang))

    booking = await create_booking(
        session,
        creator=user,
        court_id=body.court_id,
        match_type=body.match_type,
        play_date=body.play_date,
        start_time=body.start_time,
        end_time=body.end_time,
        min_ntrp=body.min_ntrp,
        max_ntrp=body.max_ntrp,
        gender_requirement=body.gender_requirement,
        cost_per_person=body.cost_per_person,
        description=body.description,
    )
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.get("", response_model=list[BookingResponse])
async def get_bookings(
    session: DbSession,
    city: str | None = Query(default=None),
    match_type: str | None = Query(default=None, pattern=r"^(singles|doubles)$"),
    gender_requirement: str | None = Query(default=None, pattern=r"^(male_only|female_only|any)$"),
):
    bookings = await list_bookings(session, city=city, match_type=match_type, gender_requirement=gender_requirement)
    return bookings


@router.get("/my", response_model=list[BookingResponse])
async def get_my_bookings(
    user: CurrentUser,
    session: DbSession,
    booking_status: str | None = Query(default=None, alias="status", pattern=r"^(open|confirmed|completed|cancelled)$"),
):
    bookings = await list_my_bookings(session, user.id, status=booking_status)
    return bookings


@router.get("/{booking_id}", response_model=BookingDetailResponse)
async def get_booking(booking_id: str, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))
    return _booking_to_detail(booking)


@router.post("/{booking_id}/join", response_model=BookingDetailResponse)
async def join_existing_booking(booking_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.status != BookingStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.not_open", lang))

    # Check if already joined
    for p in booking.participants:
        if p.user_id == user.id and p.status != ParticipantStatus.CANCELLED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("booking.already_joined", lang))

    # Check NTRP range
    user_ntrp = _ntrp_to_float(user.ntrp_level)
    min_ntrp = _ntrp_to_float(booking.min_ntrp)
    max_ntrp = _ntrp_to_float(booking.max_ntrp)
    if user_ntrp < min_ntrp or user_ntrp > max_ntrp:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.ntrp_out_of_range", lang))

    # Check gender requirement
    if booking.gender_requirement.value == "male_only" and user.gender != Gender.MALE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.gender_mismatch", lang))
    if booking.gender_requirement.value == "female_only" and user.gender != Gender.FEMALE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.gender_mismatch", lang))

    # Check if full
    accepted_count = count_accepted_participants(booking)
    if accepted_count >= booking.max_participants:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("booking.full", lang))

    await join_booking(session, booking, user)
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.post("/{booking_id}/confirm", response_model=BookingDetailResponse)
async def confirm_existing_booking(booking_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.not_creator", lang))

    if booking.status != BookingStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.not_open", lang))

    if count_accepted_participants(booking) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.not_enough_participants", lang))

    booking = await confirm_booking(session, booking)
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.post("/{booking_id}/cancel", response_model=BookingDetailResponse)
async def cancel_existing_booking(booking_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.already_cancelled", lang))

    if booking.status == BookingStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.already_cancelled", lang))

    booking = await cancel_booking(session, booking, user)
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.post("/{booking_id}/complete", response_model=BookingDetailResponse)
async def complete_existing_booking(booking_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.not_creator", lang))

    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.cannot_complete", lang))

    play_dt = datetime.combine(booking.play_date, booking.start_time, tzinfo=timezone.utc)
    if datetime.now(timezone.utc) < play_dt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.cannot_complete", lang))

    booking = await complete_booking(session, booking)
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.patch("/{booking_id}/participants/{user_id}", response_model=BookingDetailResponse)
async def manage_participant(
    booking_id: str,
    user_id: str,
    body: ParticipantUpdateRequest,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.not_creator", lang))

    participant = await update_participant_status(session, booking, uuid.UUID(user_id), body.status)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("common.not_found", lang))

    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/xue/APP && uv run python -c "from app.routers.bookings import router; print('Booking router OK')"`
Expected: `Booking router OK`

- [ ] **Step 3: Commit**

```bash
git add app/routers/bookings.py
git commit -m "feat: booking router with create, join, confirm, cancel, complete endpoints"
```

---

### Task 11: Register New Routers in App Factory

**Files:**

- Modify: `app/main.py`

- [ ] **Step 1: Update app/main.py**

In `app/main.py`, change the router imports and registration from:

```python
    from app.routers import auth, users

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
```

to:

```python
    from app.routers import auth, bookings, courts, users

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(courts.router, prefix="/api/v1/courts", tags=["courts"])
    app.include_router(bookings.router, prefix="/api/v1/bookings", tags=["bookings"])
```

- [ ] **Step 2: Verify server starts**

Run: `cd /Users/xue/APP && timeout 5 uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 || true`
Expected: Server starts without import errors (will timeout after 5s, that's fine).

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: register courts and bookings routers in app factory"
```

---

### Task 12: Booking Tests

**Files:**

- Create: `tests/test_bookings.py`

- [ ] **Step 1: Create tests/test_bookings.py**

```python
import uuid
from datetime import date, time, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
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


def _future_date() -> str:
    return (date.today() + timedelta(days=7)).isoformat()


async def _create_booking(client: AsyncClient, token: str, court_id: str) -> dict:
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "court_id": court_id,
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
            "description": "Friendly match",
        },
    )
    return resp


# --- Create Booking Tests ---

@pytest.mark.asyncio
async def test_create_booking(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "creator1")
    court = await _seed_court(session)

    resp = await _create_booking(client, token, str(court.id))
    assert resp.status_code == 201
    data = resp.json()
    assert data["match_type"] == "singles"
    assert data["status"] == "open"
    assert data["max_participants"] == 2
    assert len(data["participants"]) == 1
    assert data["participants"][0]["status"] == "accepted"
    assert data["court_name"] == "Test Court"


@pytest.mark.asyncio
async def test_create_booking_credit_too_low(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "lowcredit")
    court = await _seed_court(session)

    # Set credit score below 60
    from sqlalchemy import update
    await session.execute(update(User).where(User.id == uuid.UUID(user_id)).values(credit_score=50))
    await session.commit()

    resp = await _create_booking(client, token, str(court.id))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_booking_unapproved_court(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "badcourt")
    court = Court(name="Unapproved", address="Addr", city="HK", court_type=CourtType.INDOOR, is_approved=False)
    session.add(court)
    await session.commit()
    await session.refresh(court)

    resp = await _create_booking(client, token, str(court.id))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_booking_doubles_max_4(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "doubles1")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "court_id": str(court.id),
            "match_type": "doubles",
            "play_date": _future_date(),
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["max_participants"] == 4


# --- Join Booking Tests ---

@pytest.mark.asyncio
async def test_join_booking(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host2")
    token2, _ = await _register_and_get_token(client, "joiner2")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/join",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["participants"]) == 2


@pytest.mark.asyncio
async def test_join_booking_duplicate(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host3")
    token2, _ = await _register_and_get_token(client, "joiner3")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_join_booking_ntrp_out_of_range(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host4", ntrp="3.5")
    token2, _ = await _register_and_get_token(client, "joiner4", ntrp="5.0")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_join_booking_gender_mismatch(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host5", gender="male")
    token2, _ = await _register_and_get_token(client, "joiner5", gender="female")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "male_only",
        },
    )
    booking_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_join_booking_full(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host6")
    token2, _ = await _register_and_get_token(client, "joiner6a")
    token3, _ = await _register_and_get_token(client, "joiner6b")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # joiner6a joins (now 2/2 for singles — but joiner is pending, not accepted yet)
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})

    # Creator accepts joiner6a
    joiner6a_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner6a_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # joiner6b tries to join — should fail (full)
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token3}"})
    assert resp.status_code == 409


# --- Confirm Booking Tests ---

@pytest.mark.asyncio
async def test_confirm_booking(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host7")
    token2, _ = await _register_and_get_token(client, "joiner7")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # Join and accept
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    joiner_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Confirm
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_confirm_not_enough_participants(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host8")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_confirm_not_creator(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host9")
    token2, _ = await _register_and_get_token(client, "joiner9")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 403


# --- Cancel Booking Tests ---

@pytest.mark.asyncio
async def test_cancel_booking_by_creator(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "host10")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_first_time_no_deduction(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "host11")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {token1}"})

    # Check credit score unchanged (first cancel = warning)
    profile = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token1}"})
    assert profile.json()["credit_score"] == 80


# --- Complete Booking Tests ---

@pytest.mark.asyncio
async def test_complete_booking_awards_credit(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host12")
    token2, _ = await _register_and_get_token(client, "joiner12")
    court = await _seed_court(session)

    # Create booking with past play date for completion
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": yesterday,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    # This will fail because play_date is in the past — so we need to insert directly
    # Instead, create with future date then manually set to past
    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # Join and accept
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    joiner_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Confirm
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})

    # Manually set play_date to past so complete works
    from app.models.booking import Booking
    from sqlalchemy import update
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    # Complete
    resp = await client.post(f"/api/v1/bookings/{booking_id}/complete", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # Check both users got +5 credit
    profile1 = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token1}"})
    assert profile1.json()["credit_score"] == 85

    profile2 = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token2}"})
    assert profile2.json()["credit_score"] == 85


@pytest.mark.asyncio
async def test_complete_before_play_time_fails(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host13")
    token2, _ = await _register_and_get_token(client, "joiner13")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # Join, accept, confirm
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    joiner_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})

    # Try to complete — play date is in the future
    resp = await client.post(f"/api/v1/bookings/{booking_id}/complete", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 400


# --- List Bookings Tests ---

@pytest.mark.asyncio
async def test_list_bookings(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "lister1")
    court = await _seed_court(session)

    await _create_booking(client, token, str(court.id))

    resp = await client.get("/api/v1/bookings")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_list_my_bookings(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "mylist1")
    token2, _ = await _register_and_get_token(client, "mylist2")
    court = await _seed_court(session)

    await _create_booking(client, token1, str(court.id))
    await _create_booking(client, token2, str(court.id))

    resp = await client.get("/api/v1/bookings/my", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --- Participant Management Tests ---

@pytest.mark.asyncio
async def test_accept_participant(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host14")
    token2, _ = await _register_and_get_token(client, "joiner14")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})

    detail = await client.get(f"/api/v1/bookings/{booking_id}")
    joiner_id = detail.json()["participants"][1]["user_id"]
    assert detail.json()["participants"][1]["status"] == "pending"

    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )
    assert resp.status_code == 200
    accepted = [p for p in resp.json()["participants"] if p["user_id"] == joiner_id]
    assert accepted[0]["status"] == "accepted"


@pytest.mark.asyncio
async def test_reject_participant(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host15")
    token2, _ = await _register_and_get_token(client, "joiner15")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})

    detail = await client.get(f"/api/v1/bookings/{booking_id}")
    joiner_id = detail.json()["participants"][1]["user_id"]

    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "rejected"},
    )
    assert resp.status_code == 200
    rejected = [p for p in resp.json()["participants"] if p["user_id"] == joiner_id]
    assert rejected[0]["status"] == "rejected"
```

- [ ] **Step 2: Run booking tests**

Run: `cd /Users/xue/APP && uv run pytest tests/test_bookings.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_bookings.py
git commit -m "feat: comprehensive booking tests covering full lifecycle"
```

---

### Task 13: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/xue/APP && uv run pytest tests/ -v --tb=short`
Expected: All tests PASS (existing + new court + booking tests)

- [ ] **Step 2: Start the server to verify**

```bash
cd /Users/xue/APP && timeout 5 uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 || true
```

Expected: Server starts without errors, exits after timeout.

- [ ] **Step 3: Verify Swagger docs**

Visit `http://localhost:8000/docs` — should show all endpoints including courts and bookings.

- [ ] **Step 4: Commit any remaining changes**

Run: `cd /Users/xue/APP && git status`

If any unstaged changes, add and commit:

```bash
git add -A
git commit -m "chore: Phase 2 final cleanup"
```

---

## Verification Checklist

After completing all tasks, verify:

1. `uv run pytest tests/ -v` — all tests pass
2. `uv run uvicorn app.main:app` — server starts without errors
3. `GET /api/v1/courts` — returns list of approved courts
4. `POST /api/v1/courts` — user can submit a court (unapproved)
5. `POST /api/v1/bookings` — creates booking, creator auto-joins as accepted
6. `POST /api/v1/bookings/{id}/join` — validates NTRP range, gender, capacity
7. `PATCH /api/v1/bookings/{id}/participants/{uid}` — creator accepts/rejects
8. `POST /api/v1/bookings/{id}/confirm` — requires ≥2 accepted participants
9. `POST /api/v1/bookings/{id}/cancel` — applies correct credit penalty tier
10. `POST /api/v1/bookings/{id}/complete` — awards +5 credit to accepted participants
11. `GET /api/v1/bookings/my` — returns user's bookings
12. First cancellation is warning-only (no credit deduction)
13. i18n returns correct translations for booking/court error messages
