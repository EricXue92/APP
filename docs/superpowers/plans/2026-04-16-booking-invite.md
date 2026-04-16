# Booking Invite (私信约球) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to directly invite a specific friend to play tennis, skipping NTRP level validation.

**Architecture:** New `BookingInvite` model with `pending → accepted/rejected/expired` lifecycle. On accept, reuses existing `create_booking()` + `confirm_booking()` to create a confirmed Booking + ChatRoom. Follows the same pattern as `MatchProposal`.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Alembic, pytest

---

### Task 1: Model — BookingInvite

**Files:**

- Create: `app/models/booking_invite.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/notification.py`

- [ ] **Step 1: Create `app/models/booking_invite.py`**

```python
import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.booking import GenderRequirement, MatchType


class InviteStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class BookingInvite(Base):
    __tablename__ = "booking_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inviter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    invitee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    court_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courts.id", ondelete="CASCADE"))
    match_type: Mapped[MatchType] = mapped_column(Enum(MatchType))
    play_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    gender_requirement: Mapped[GenderRequirement] = mapped_column(Enum(GenderRequirement), default=GenderRequirement.ANY)
    cost_per_person: Mapped[int | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InviteStatus] = mapped_column(Enum(InviteStatus), default=InviteStatus.PENDING)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    inviter: Mapped["User"] = relationship(foreign_keys=[inviter_id])
    invitee: Mapped["User"] = relationship(foreign_keys=[invitee_id])
    court: Mapped["Court"] = relationship(foreign_keys=[court_id])
```

- [ ] **Step 2: Add notification types to `app/models/notification.py`**

Add three new enum values at the end of `NotificationType`:

```python
    BOOKING_INVITE_RECEIVED = "booking_invite_received"
    BOOKING_INVITE_ACCEPTED = "booking_invite_accepted"
    BOOKING_INVITE_REJECTED = "booking_invite_rejected"
```

- [ ] **Step 3: Register model in `app/models/__init__.py`**

Add import:

```python
from app.models.booking_invite import BookingInvite
```

Add `"BookingInvite"` to the `__all__` list.

- [ ] **Step 4: Update `tests/conftest.py` import**

Add `BookingInvite` to the import line from `app.models`:

```python
from app.models import Booking, BookingParticipant, Block, BookingInvite, Court, ...  # noqa: F401
```

- [ ] **Step 5: Run tests to verify model loads**

Run: `uv run pytest tests/test_auth.py::test_login_username -v`
Expected: PASS (proves model loads without errors)

- [ ] **Step 6: Commit**

```bash
git add app/models/booking_invite.py app/models/__init__.py app/models/notification.py tests/conftest.py
git commit -m "feat(invite): add BookingInvite model and notification types"
```

---

### Task 2: Schema — request/response types

**Files:**

- Create: `app/schemas/booking_invite.py`

- [ ] **Step 1: Create `app/schemas/booking_invite.py`**

```python
import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


class BookingInviteCreateRequest(BaseModel):
    invitee_id: uuid.UUID
    court_id: uuid.UUID
    match_type: str = Field(..., pattern=r"^(singles|doubles)$")
    play_date: date
    start_time: time
    end_time: time
    gender_requirement: str = Field(default="any", pattern=r"^(male_only|female_only|any)$")
    cost_per_person: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)


class BookingInviteResponse(BaseModel):
    id: uuid.UUID
    inviter_id: uuid.UUID
    invitee_id: uuid.UUID
    court_id: uuid.UUID
    match_type: str
    play_date: date
    start_time: time
    end_time: time
    gender_requirement: str
    cost_per_person: int | None
    description: str | None
    status: str
    booking_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/booking_invite.py
git commit -m "feat(invite): add booking invite schemas"
```

---

### Task 3: Service — core business logic

**Files:**

- Create: `app/services/booking_invite.py`

- [ ] **Step 1: Create `app/services/booking_invite.py`**

```python
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import BookingParticipant, BookingStatus, MatchType, ParticipantStatus
from app.models.booking_invite import BookingInvite, InviteStatus
from app.models.court import Court
from app.models.notification import NotificationType
from app.models.user import User
from app.services.block import is_blocked
from app.services.booking import create_booking
from app.services.chat import create_chat_room
from app.services.notification import create_notification
from app.services.user import get_user_by_id


async def _load_invite(session: AsyncSession, invite_id: uuid.UUID) -> BookingInvite | None:
    result = await session.execute(
        select(BookingInvite)
        .options(
            selectinload(BookingInvite.inviter),
            selectinload(BookingInvite.invitee),
            selectinload(BookingInvite.court),
        )
        .where(BookingInvite.id == invite_id)
    )
    return result.scalar_one_or_none()


def _check_expired(invite: BookingInvite) -> bool:
    """Mark invite as expired if play_date has passed. Returns True if expired."""
    if invite.status == InviteStatus.PENDING and invite.play_date < date.today():
        invite.status = InviteStatus.EXPIRED
        return True
    return False


async def create_invite(
    session: AsyncSession,
    *,
    inviter: User,
    invitee_id: uuid.UUID,
    court_id: uuid.UUID,
    match_type: str,
    play_date: date,
    start_time: datetime.time,
    end_time: datetime.time,
    gender_requirement: str = "any",
    cost_per_person: int | None = None,
    description: str | None = None,
) -> BookingInvite:
    # Cannot invite self
    if inviter.id == invitee_id:
        raise ValueError("cannot_invite_self")

    # Check invitee exists
    invitee = await get_user_by_id(session, invitee_id)
    if invitee is None:
        raise ValueError("invitee_not_found")

    # Check block
    if await is_blocked(session, inviter.id, invitee_id):
        raise ValueError("blocked")

    # Check duplicate pending
    existing = await session.execute(
        select(BookingInvite).where(
            BookingInvite.inviter_id == inviter.id,
            BookingInvite.invitee_id == invitee_id,
            BookingInvite.status == InviteStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError("duplicate_pending")

    invite = BookingInvite(
        inviter_id=inviter.id,
        invitee_id=invitee_id,
        court_id=court_id,
        match_type=MatchType(match_type),
        play_date=play_date,
        start_time=start_time,
        end_time=end_time,
        gender_requirement=gender_requirement,
        cost_per_person=cost_per_person,
        description=description,
    )
    session.add(invite)

    await create_notification(
        session,
        recipient_id=invitee_id,
        type=NotificationType.BOOKING_INVITE_RECEIVED,
        actor_id=inviter.id,
        target_type="booking_invite",
        target_id=invite.id,
    )

    await session.commit()
    return await _load_invite(session, invite.id)


async def accept_invite(
    session: AsyncSession,
    *,
    invite_id: uuid.UUID,
    invitee: User,
) -> BookingInvite:
    invite = await _load_invite(session, invite_id)
    if invite is None:
        raise ValueError("invite_not_found")

    if invite.invitee_id != invitee.id:
        raise PermissionError("not_invitee")

    _check_expired(invite)
    if invite.status != InviteStatus.PENDING:
        raise ValueError("invite_not_pending")

    invite.status = InviteStatus.ACCEPTED

    inviter = await get_user_by_id(session, invite.inviter_id)

    # Determine NTRP range from both players (for record-keeping)
    from app.services.booking import _ntrp_to_float
    inviter_ntrp = _ntrp_to_float(inviter.ntrp_level)
    invitee_ntrp = _ntrp_to_float(invitee.ntrp_level)
    min_ntrp = inviter.ntrp_level if inviter_ntrp <= invitee_ntrp else invitee.ntrp_level
    max_ntrp = invitee.ntrp_level if invitee_ntrp >= inviter_ntrp else inviter.ntrp_level

    # Create booking (inviter as creator)
    booking = await create_booking(
        session,
        creator=inviter,
        court_id=invite.court_id,
        match_type=invite.match_type.value,
        play_date=invite.play_date,
        start_time=invite.start_time,
        end_time=invite.end_time,
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_requirement=invite.gender_requirement.value if hasattr(invite.gender_requirement, 'value') else invite.gender_requirement,
        cost_per_person=invite.cost_per_person,
        description=invite.description,
    )

    # Add invitee as accepted participant
    participant = BookingParticipant(
        booking_id=booking.id,
        user_id=invitee.id,
        status=ParticipantStatus.ACCEPTED,
    )
    session.add(participant)
    await session.flush()

    # Set booking to confirmed
    booking.status = BookingStatus.CONFIRMED
    await session.flush()

    # Create chat room
    court = invite.court or await session.get(Court, invite.court_id)
    court_name = court.name if court else ""
    await create_chat_room(
        session,
        booking=booking,
        participant_ids=[inviter.id, invitee.id],
        court_name=court_name,
    )

    invite.booking_id = booking.id

    await create_notification(
        session,
        recipient_id=invite.inviter_id,
        type=NotificationType.BOOKING_INVITE_ACCEPTED,
        actor_id=invitee.id,
        target_type="booking_invite",
        target_id=invite.id,
    )

    await session.commit()
    return await _load_invite(session, invite.id)


async def reject_invite(
    session: AsyncSession,
    *,
    invite_id: uuid.UUID,
    invitee: User,
) -> BookingInvite:
    invite = await _load_invite(session, invite_id)
    if invite is None:
        raise ValueError("invite_not_found")

    if invite.invitee_id != invitee.id:
        raise PermissionError("not_invitee")

    _check_expired(invite)
    if invite.status != InviteStatus.PENDING:
        raise ValueError("invite_not_pending")

    invite.status = InviteStatus.REJECTED

    await create_notification(
        session,
        recipient_id=invite.inviter_id,
        type=NotificationType.BOOKING_INVITE_REJECTED,
        actor_id=invitee.id,
        target_type="booking_invite",
        target_id=invite.id,
    )

    await session.commit()
    return await _load_invite(session, invite.id)


async def get_invite_by_id(session: AsyncSession, invite_id: uuid.UUID) -> BookingInvite | None:
    invite = await _load_invite(session, invite_id)
    if invite and _check_expired(invite):
        await session.commit()
    return invite


async def list_sent_invites(session: AsyncSession, user_id: uuid.UUID) -> list[BookingInvite]:
    result = await session.execute(
        select(BookingInvite)
        .options(
            selectinload(BookingInvite.inviter),
            selectinload(BookingInvite.invitee),
            selectinload(BookingInvite.court),
        )
        .where(BookingInvite.inviter_id == user_id)
        .order_by(BookingInvite.created_at.desc())
    )
    return list(result.scalars().all())


async def list_received_invites(session: AsyncSession, user_id: uuid.UUID) -> list[BookingInvite]:
    result = await session.execute(
        select(BookingInvite)
        .options(
            selectinload(BookingInvite.inviter),
            selectinload(BookingInvite.invitee),
            selectinload(BookingInvite.court),
        )
        .where(BookingInvite.invitee_id == user_id)
        .order_by(BookingInvite.created_at.desc())
    )
    invites = list(result.scalars().all())

    # Lazy expiry for pending invites
    expired_any = False
    for inv in invites:
        if _check_expired(inv):
            expired_any = True
    if expired_any:
        await session.commit()

    return invites
```

- [ ] **Step 2: Commit**

```bash
git add app/services/booking_invite.py
git commit -m "feat(invite): add booking invite service layer"
```

---

### Task 4: i18n — add translation keys

**Files:**

- Modify: `app/i18n.py`

- [ ] **Step 1: Add invite translation keys to `app/i18n.py`**

Add the following entries to the `_MESSAGES` dict (before the closing `}`):

```python
    "invite.not_found": {
        "zh-Hans": "邀请未找到",
        "zh-Hant": "邀請未找到",
        "en": "Invite not found",
    },
    "invite.not_pending": {
        "zh-Hans": "邀请已处理",
        "zh-Hant": "邀請已處理",
        "en": "Invite is no longer pending",
    },
    "invite.cannot_invite_self": {
        "zh-Hans": "不能邀请自己",
        "zh-Hant": "不能邀請自己",
        "en": "Cannot invite yourself",
    },
    "invite.duplicate_pending": {
        "zh-Hans": "你已向该用户发送了邀请",
        "zh-Hant": "你已向該用戶發送了邀請",
        "en": "You already have a pending invite to this user",
    },
    "invite.invitee_not_found": {
        "zh-Hans": "被邀请人不存在",
        "zh-Hant": "被邀請人不存在",
        "en": "Invitee not found",
    },
    "invite.not_invitee": {
        "zh-Hans": "只有被邀请人才能回应",
        "zh-Hant": "只有被邀請人才能回應",
        "en": "Only the invitee can respond",
    },
    "invite.not_participant": {
        "zh-Hans": "你不是该邀请的参与方",
        "zh-Hant": "你不是該邀請的參與方",
        "en": "You are not a participant of this invite",
    },
    "push.booking_invite_received.title": {
        "zh-Hant": "收到約球邀請",
        "zh-Hans": "收到约球邀请",
        "en": "Booking Invite Received",
    },
    "push.booking_invite_received.body": {
        "zh-Hant": "有人邀請您一起打球",
        "zh-Hans": "有人邀请您一起打球",
        "en": "Someone invited you to play tennis",
    },
```

- [ ] **Step 2: Commit**

```bash
git add app/i18n.py
git commit -m "feat(invite): add i18n translations for booking invite"
```

---

### Task 5: Router — API endpoints

**Files:**

- Create: `app/routers/booking_invite.py`
- Modify: `app/main.py`

- [ ] **Step 1: Create `app/routers/booking_invite.py`**

```python
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.booking_invite import BookingInviteCreateRequest, BookingInviteResponse
from app.services.booking_invite import (
    accept_invite,
    create_invite,
    get_invite_by_id,
    list_received_invites,
    list_sent_invites,
    reject_invite,
)
from app.services.court import get_court_by_id

router = APIRouter()


def _to_response(invite) -> BookingInviteResponse:
    return BookingInviteResponse(
        id=invite.id,
        inviter_id=invite.inviter_id,
        invitee_id=invite.invitee_id,
        court_id=invite.court_id,
        match_type=invite.match_type.value,
        play_date=invite.play_date,
        start_time=invite.start_time,
        end_time=invite.end_time,
        gender_requirement=invite.gender_requirement.value if hasattr(invite.gender_requirement, 'value') else invite.gender_requirement,
        cost_per_person=invite.cost_per_person,
        description=invite.description,
        status=invite.status.value,
        booking_id=invite.booking_id,
        created_at=invite.created_at,
    )


@router.post("", response_model=BookingInviteResponse, status_code=status.HTTP_201_CREATED)
async def create_booking_invite(
    body: BookingInviteCreateRequest, user: CurrentUser, session: DbSession, lang: Lang
):
    if user.credit_score < 60:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.credit_too_low", lang))

    court = await get_court_by_id(session, body.court_id)
    if court is None or not court.is_approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("court.not_found", lang))

    if body.play_date < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.play_date_past", lang))

    try:
        invite = await create_invite(
            session,
            inviter=user,
            invitee_id=body.invitee_id,
            court_id=body.court_id,
            match_type=body.match_type,
            play_date=body.play_date,
            start_time=body.start_time,
            end_time=body.end_time,
            gender_requirement=body.gender_requirement,
            cost_per_person=body.cost_per_person,
            description=body.description,
        )
    except ValueError as e:
        msg = str(e)
        if msg == "cannot_invite_self":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("invite.cannot_invite_self", lang))
        if msg == "invitee_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("invite.invitee_not_found", lang))
        if msg == "blocked":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("block.user_blocked", lang))
        raise
    except LookupError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("invite.duplicate_pending", lang))

    return _to_response(invite)


@router.get("/sent", response_model=list[BookingInviteResponse])
async def get_sent_invites(user: CurrentUser, session: DbSession):
    invites = await list_sent_invites(session, user.id)
    return [_to_response(inv) for inv in invites]


@router.get("/received", response_model=list[BookingInviteResponse])
async def get_received_invites(user: CurrentUser, session: DbSession):
    invites = await list_received_invites(session, user.id)
    return [_to_response(inv) for inv in invites]


@router.get("/{invite_id}", response_model=BookingInviteResponse)
async def get_invite(invite_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    invite = await get_invite_by_id(session, uuid.UUID(invite_id))
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("invite.not_found", lang))
    if invite.inviter_id != user.id and invite.invitee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("invite.not_participant", lang))
    return _to_response(invite)


@router.post("/{invite_id}/accept", response_model=BookingInviteResponse)
async def accept_booking_invite(invite_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        invite = await accept_invite(session, invite_id=uuid.UUID(invite_id), invitee=user)
    except ValueError as e:
        msg = str(e)
        if msg == "invite_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("invite.not_found", lang))
        if msg == "invite_not_pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("invite.not_pending", lang))
        raise
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("invite.not_invitee", lang))
    return _to_response(invite)


@router.post("/{invite_id}/reject", response_model=BookingInviteResponse)
async def reject_booking_invite(invite_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        invite = await reject_invite(session, invite_id=uuid.UUID(invite_id), invitee=user)
    except ValueError as e:
        msg = str(e)
        if msg == "invite_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("invite.not_found", lang))
        if msg == "invite_not_pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("invite.not_pending", lang))
        raise
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("invite.not_invitee", lang))
    return _to_response(invite)
```

- [ ] **Step 2: Register router in `app/main.py`**

Add to the import line:

```python
from app.routers import auth, assistant, blocks, booking_invite, bookings, chat, courts, devices, events, follows, matching, notifications, reports, reviews, users, weather
```

Add after the bookings router registration:

```python
    app.include_router(booking_invite.router, prefix="/api/v1/bookings/invites", tags=["booking-invites"])
```

- [ ] **Step 3: Run server smoke test**

Run: `uv run python -c "from app.main import create_app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/routers/booking_invite.py app/main.py
git commit -m "feat(invite): add booking invite router and register in app"
```

---

### Task 6: Tests — create invite

**Files:**

- Create: `tests/test_booking_invite.py`

- [ ] **Step 1: Write test file with helpers and create-invite tests**

```python
import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.notification import NotificationType
from app.models.booking_invite import InviteStatus


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


def _invite_body(invitee_id: str, court_id: str, **overrides) -> dict:
    body = {
        "invitee_id": invitee_id,
        "court_id": court_id,
        "match_type": "singles",
        "play_date": str(date.today() + timedelta(days=3)),
        "start_time": "14:00:00",
        "end_time": "16:00:00",
    }
    body.update(overrides)
    return body


# --- Create invite tests ---


@pytest.mark.asyncio
async def test_create_invite_success(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_a")
    _, user_b = await _register_and_get_token(client, "inv_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["inviter_id"] == user_a
    assert data["invitee_id"] == user_b
    assert data["status"] == "pending"
    assert data["booking_id"] is None


@pytest.mark.asyncio
async def test_create_invite_self(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_self")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_a, str(court.id)),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_invite_duplicate_pending(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_dup_a")
    _, user_b = await _register_and_get_token(client, "inv_dup_b")
    court = await _seed_court(session)

    body = _invite_body(user_b, str(court.id))
    resp1 = await client.post("/api/v1/bookings/invites", headers=_auth(token_a), json=body)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/bookings/invites", headers=_auth(token_a), json=body)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_invite_past_date(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_past_a")
    _, user_b = await _register_and_get_token(client, "inv_past_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id), play_date=str(date.today() - timedelta(days=1))),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_invite_blocked(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_blk_a")
    token_b, user_b = await _register_and_get_token(client, "inv_blk_b")
    court = await _seed_court(session)

    # B blocks A
    await client.post(f"/api/v1/blocks/{user_a}", headers=_auth(token_b))

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_invite_low_credit(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_lowcr_a")
    _, user_b = await _register_and_get_token(client, "inv_lowcr_b")
    court = await _seed_court(session)

    # Set credit below 60
    from app.models.user import User
    from sqlalchemy import select
    result = await session.execute(select(User).where(User.id == uuid.UUID(user_a)))
    u = result.scalar_one()
    u.credit_score = 50
    await session.commit()

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_booking_invite.py -v`
Expected: All 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_booking_invite.py
git commit -m "test(invite): add create invite tests"
```

---

### Task 7: Tests — accept, reject, list, detail

**Files:**

- Modify: `tests/test_booking_invite.py`

- [ ] **Step 1: Append accept/reject/list/detail tests to `tests/test_booking_invite.py`**

```python
# --- Accept invite tests ---


@pytest.mark.asyncio
async def test_accept_invite(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_acc_a")
    token_b, user_b = await _register_and_get_token(client, "inv_acc_b")
    court = await _seed_court(session)

    # Create invite
    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # Accept
    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/accept",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["booking_id"] is not None

    # Verify booking was created and confirmed
    booking_resp = await client.get(
        f"/api/v1/bookings/{data['booking_id']}",
        headers=_auth(token_a),
    )
    assert booking_resp.status_code == 200
    assert booking_resp.json()["status"] == "confirmed"
    assert len(booking_resp.json()["participants"]) == 2


@pytest.mark.asyncio
async def test_accept_invite_not_invitee(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_notinv_a")
    _, user_b = await _register_and_get_token(client, "inv_notinv_b")
    token_c, _ = await _register_and_get_token(client, "inv_notinv_c")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # C tries to accept
    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/accept",
        headers=_auth(token_c),
    )
    assert resp.status_code == 403


# --- Reject invite tests ---


@pytest.mark.asyncio
async def test_reject_invite(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_rej_a")
    token_b, user_b = await _register_and_get_token(client, "inv_rej_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/reject",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_accept_already_rejected(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_rejed_a")
    token_b, user_b = await _register_and_get_token(client, "inv_rejed_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # Reject first
    await client.post(f"/api/v1/bookings/invites/{invite_id}/reject", headers=_auth(token_b))

    # Try to accept
    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/accept",
        headers=_auth(token_b),
    )
    assert resp.status_code == 400


# --- List & detail tests ---


@pytest.mark.asyncio
async def test_list_sent_invites(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_ls_a")
    _, user_b = await _register_and_get_token(client, "inv_ls_b")
    court = await _seed_court(session)

    await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )

    resp = await client.get("/api/v1/bookings/invites/sent", headers=_auth(token_a))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_list_received_invites(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_lr_a")
    token_b, user_b = await _register_and_get_token(client, "inv_lr_b")
    court = await _seed_court(session)

    await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )

    resp = await client.get("/api/v1/bookings/invites/received", headers=_auth(token_b))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_invite_detail(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_det_a")
    token_b, user_b = await _register_and_get_token(client, "inv_det_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # Both parties can see detail
    resp_a = await client.get(f"/api/v1/bookings/invites/{invite_id}", headers=_auth(token_a))
    assert resp_a.status_code == 200

    resp_b = await client.get(f"/api/v1/bookings/invites/{invite_id}", headers=_auth(token_b))
    assert resp_b.status_code == 200


@pytest.mark.asyncio
async def test_get_invite_detail_forbidden(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_forb_a")
    _, user_b = await _register_and_get_token(client, "inv_forb_b")
    token_c, _ = await _register_and_get_token(client, "inv_forb_c")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # C cannot see
    resp_c = await client.get(f"/api/v1/bookings/invites/{invite_id}", headers=_auth(token_c))
    assert resp_c.status_code == 403
```

- [ ] **Step 2: Run all invite tests**

Run: `uv run pytest tests/test_booking_invite.py -v`
Expected: All 14 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_booking_invite.py
git commit -m "test(invite): add accept, reject, list, and detail tests"
```

---

### Task 8: Migration — create booking_invites table

**Files:**

- Create: Alembic migration file (auto-generated)

- [ ] **Step 1: Generate migration**

Run: `uv run alembic revision --autogenerate -m "add booking_invites table and invite notification types"`

- [ ] **Step 2: Review the generated migration**

Open the generated file and verify it contains:

- `op.create_table('booking_invites', ...)` with all columns
- Enum additions for `notificationtype` (3 new values) and `invitestatus`
- No unexpected changes

- [ ] **Step 3: Apply migration**

Run: `uv run alembic upgrade head`
Expected: No errors

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "migration: add booking_invites table and invite notification types"
```
