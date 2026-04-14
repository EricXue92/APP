# Phase 5 — Notification System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-app notification system that creates notifications for booking, follow, review, and moderation events, with REST API endpoints for listing, reading, and counting notifications.

**Architecture:** Direct service-to-service notification creation — existing services call `create_notification()` at their trigger points. A new `Notification` model stores events, a new `notification` service handles CRUD, and a new `notifications` router exposes 4 endpoints. No event bus, no push delivery.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Alembic, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `app/models/notification.py` | Notification model + NotificationType enum |
| Create | `app/services/notification.py` | create, list, count, mark-read logic |
| Create | `app/schemas/notification.py` | NotificationResponse + UnreadCountResponse |
| Create | `app/routers/notifications.py` | 4 REST endpoints |
| Create | `tests/test_notifications.py` | All notification tests |
| Modify | `app/models/__init__.py` | Export Notification model |
| Modify | `app/main.py` | Register notifications router |
| Modify | `app/services/follow.py` | Add notification calls in create_follow |
| Modify | `app/services/booking.py` | Add notification calls in join/respond/cancel/confirm/complete |
| Modify | `app/services/review.py` | Add notification call in submit_review on reveal |
| Modify | `app/services/report.py` | Add notification calls in resolve_report |
| Modify | `tests/conftest.py` | Import Notification model so tables are created in tests |
| Create | Alembic migration | Add notifications table |

---

### Task 1: Notification Model

**Files:**
- Create: `app/models/notification.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Create the Notification model**

Create `app/models/notification.py`:

```python
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
```

- [ ] **Step 2: Export from models __init__**

In `app/models/__init__.py`, add the import:

```python
from app.models.notification import Notification
```

And add `"Notification"` to the `__all__` list.

- [ ] **Step 3: Update tests/conftest.py import**

In `tests/conftest.py`, add `Notification` to the existing import line:

```python
from app.models import Booking, BookingParticipant, Block, Court, CreditLog, Follow, Notification, Report, Review, User, UserAuth  # noqa: F401
```

- [ ] **Step 4: Generate Alembic migration**

Run:
```bash
uv run alembic revision --autogenerate -m "add notifications table"
```

Expected: A new migration file is created in `alembic/versions/`.

- [ ] **Step 5: Apply migration**

Run:
```bash
uv run alembic upgrade head
```

Expected: Migration applies successfully, `notifications` table exists in dev DB.

- [ ] **Step 6: Commit**

```bash
git add app/models/notification.py app/models/__init__.py tests/conftest.py alembic/versions/
git commit -m "feat: add Notification model and migration"
```

---

### Task 2: Notification Schema

**Files:**
- Create: `app/schemas/notification.py`

- [ ] **Step 1: Create the schema file**

Create `app/schemas/notification.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    type: str
    target_type: str | None
    target_id: uuid.UUID | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    unread_count: int
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/notification.py
git commit -m "feat: add notification schemas"
```

---

### Task 3: Notification Service

**Files:**
- Create: `app/services/notification.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write failing tests for the notification service (via API)**

Create `tests/test_notifications.py`:

```python
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_empty_notifications(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_empty")

    resp = await client.get("/api/v1/notifications", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_unread_count_empty(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_count0")

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"unread_count": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_notifications.py::test_empty_notifications tests/test_notifications.py::test_unread_count_empty -v
```

Expected: FAIL — 404 because the router doesn't exist yet.

- [ ] **Step 3: Create the notification service**

Create `app/services/notification.py`:

```python
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType


async def create_notification(
    session: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    type: NotificationType,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
) -> Notification:
    notification = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        type=type,
        target_type=target_type,
        target_id=target_id,
    )
    session.add(notification)
    await session.flush()
    return notification


async def list_notifications(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    result = await session.execute(
        select(Notification)
        .where(Notification.recipient_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    return result.scalar_one()


async def mark_as_read(
    session: AsyncSession,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_id == user_id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise LookupError("Notification not found")
    notification.is_read = True
    await session.flush()


async def mark_all_as_read(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(Notification)
        .where(
            Notification.recipient_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    await session.flush()
```

- [ ] **Step 4: Create the notifications router**

Create `app/routers/notifications.py`:

```python
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.notification import NotificationResponse, UnreadCountResponse
from app.services.notification import get_unread_count, list_notifications, mark_all_as_read, mark_as_read

router = APIRouter()


@router.get("", response_model=list[NotificationResponse])
async def get_notifications(
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_notifications(session, user.id, limit=limit, offset=offset)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_notification_unread_count(user: CurrentUser, session: DbSession):
    count = await get_unread_count(session, user.id)
    return UnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_notification(notification_id: str, user: CurrentUser, session: DbSession):
    try:
        await mark_as_read(session, user.id, uuid.UUID(notification_id))
        await session.commit()
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")


@router.patch("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_notifications(user: CurrentUser, session: DbSession):
    await mark_all_as_read(session, user.id)
    await session.commit()
```

- [ ] **Step 5: Register the router in app/main.py**

In `app/main.py`, add the import and router registration:

```python
from app.routers import auth, blocks, bookings, courts, follows, notifications, reports, reviews, users
```

Add after the follows router line:

```python
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_notifications.py::test_empty_notifications tests/test_notifications.py::test_unread_count_empty -v
```

Expected: Both PASS.

- [ ] **Step 7: Commit**

```bash
git add app/services/notification.py app/routers/notifications.py app/main.py
git commit -m "feat: add notification service and router with list/count endpoints"
```

---

### Task 4: Mark-as-Read Tests and Verification

**Files:**
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write mark-as-read tests**

Append to `tests/test_notifications.py`:

```python
@pytest.mark.asyncio
async def test_mark_as_read(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_read1")
    token2, uid2 = await _register_and_get_token(client, "notif_read2")

    # Follow to create a notification
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    # uid1 should have 1 unread notification
    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 1

    # Get the notification
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    assert len(notifs) == 1
    assert notifs[0]["is_read"] is False
    notif_id = notifs[0]["id"]

    # Mark as read
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204

    # Unread count should be 0
    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_as_read_idempotent(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_idemp1")
    token2, uid2 = await _register_and_get_token(client, "notif_idemp2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notif_id = resp.json()[0]["id"]

    # Mark read twice — both should succeed
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_mark_as_read_wrong_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_wrong1")
    token2, uid2 = await _register_and_get_token(client, "notif_wrong2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notif_id = resp.json()[0]["id"]

    # uid2 tries to mark uid1's notification — should 404
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token2))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_as_read_nonexistent(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_ghost")
    fake_id = str(uuid.uuid4())

    resp = await client.patch(f"/api/v1/notifications/{fake_id}/read", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_as_read(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_all1")
    token2, uid2 = await _register_and_get_token(client, "notif_all2")
    token3, uid3 = await _register_and_get_token(client, "notif_all3")

    # Two follows → two notifications for uid1
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token3))

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 2

    # Mark all read
    resp = await client.patch("/api/v1/notifications/read-all", headers=_auth(token1))
    assert resp.status_code == 204

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 0
```

Note: these tests depend on the follow → notification integration (Task 6). They will fail until Task 6 is complete. That's expected — we write them now and they'll pass after Task 6.

- [ ] **Step 2: Commit the tests**

```bash
git add tests/test_notifications.py
git commit -m "test: add notification read management tests"
```

---

### Task 5: Pagination Test

**Files:**
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write pagination test**

Append to `tests/test_notifications.py`:

```python
@pytest.mark.asyncio
async def test_list_notifications_pagination(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_page1")

    # Create 3 followers → 3 notifications for uid1
    for i in range(3):
        tok, _ = await _register_and_get_token(client, f"notif_pager{i}")
        await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(tok))

    # Get all
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    assert len(resp.json()) == 3

    # Get first 2
    resp = await client.get("/api/v1/notifications?limit=2&offset=0", headers=_auth(token1))
    assert len(resp.json()) == 2

    # Get remaining
    resp = await client.get("/api/v1/notifications?limit=2&offset=2", headers=_auth(token1))
    assert len(resp.json()) == 1
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_notifications.py
git commit -m "test: add notification pagination test"
```

---

### Task 6: Follow → Notification Integration

**Files:**
- Modify: `app/services/follow.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write failing integration test for follow notifications**

Append to `tests/test_notifications.py`:

```python
@pytest.mark.asyncio
async def test_follow_creates_new_follower_notification(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "fnotif1")
    token2, uid2 = await _register_and_get_token(client, "fnotif2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    assert len(notifs) == 1
    assert notifs[0]["type"] == "new_follower"
    assert notifs[0]["actor_id"] == uid2
    assert notifs[0]["target_type"] == "follow"


@pytest.mark.asyncio
async def test_mutual_follow_creates_new_mutual_notification(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "mnotif1")
    token2, uid2 = await _register_and_get_token(client, "mnotif2")

    # A follows B → B gets new_follower
    await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))

    # B follows A → A gets new_follower, AND A gets new_mutual
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    # A should have: new_follower (from B) + new_mutual (B followed back)
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    types = [n["type"] for n in notifs]
    assert "new_follower" in types
    assert "new_mutual" in types

    # B should have: new_follower (from A)
    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    assert len(notifs) == 1
    assert notifs[0]["type"] == "new_follower"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_notifications.py::test_follow_creates_new_follower_notification tests/test_notifications.py::test_mutual_follow_creates_new_mutual_notification -v
```

Expected: FAIL — notifications list is empty because follow service doesn't create notifications yet.

- [ ] **Step 3: Add notification calls to follow service**

In `app/services/follow.py`, add the import at the top:

```python
from app.models.notification import NotificationType
from app.services.notification import create_notification
```

Then in the `create_follow` function, after `await session.refresh(follow)` and after computing `mutual`, add before the return:

```python
    # Notify followed user
    await create_notification(
        session,
        recipient_id=followed_id,
        type=NotificationType.NEW_FOLLOWER,
        actor_id=follower_id,
        target_type="follow",
        target_id=follow.id,
    )

    # If mutual, notify the original follower
    if mutual:
        await create_notification(
            session,
            recipient_id=follower_id,
            type=NotificationType.NEW_MUTUAL,
            actor_id=followed_id,
            target_type="follow",
            target_id=follow.id,
        )

    await session.commit()
```

Also remove the earlier `await session.commit()` that happens right after `session.add(follow)` — move the commit to after the notifications so everything is in one transaction. The full flow becomes: add follow → flush → create notifications → commit.

Change `session.add(follow)` / `await session.commit()` / `await session.refresh(follow)` to:

```python
    follow = Follow(follower_id=follower_id, followed_id=followed_id)
    session.add(follow)
    await session.flush()
    await session.refresh(follow)

    # Compute is_mutual
    mutual = await _check_reverse(session, follower_id, followed_id)

    # Notify followed user
    await create_notification(
        session,
        recipient_id=followed_id,
        type=NotificationType.NEW_FOLLOWER,
        actor_id=follower_id,
        target_type="follow",
        target_id=follow.id,
    )

    # If mutual, notify the original follower
    if mutual:
        await create_notification(
            session,
            recipient_id=follower_id,
            type=NotificationType.NEW_MUTUAL,
            actor_id=followed_id,
            target_type="follow",
            target_id=follow.id,
        )

    await session.commit()

    return _to_dict(follow, mutual)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_notifications.py::test_follow_creates_new_follower_notification tests/test_notifications.py::test_mutual_follow_creates_new_mutual_notification -v
```

Expected: Both PASS.

- [ ] **Step 5: Run all follow tests to check for regressions**

Run:
```bash
uv run pytest tests/test_follows.py -v
```

Expected: All existing follow tests still PASS.

- [ ] **Step 6: Now run the mark-as-read tests (from Task 4) which depend on follow notifications**

Run:
```bash
uv run pytest tests/test_notifications.py -v
```

Expected: All notification tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/services/follow.py tests/test_notifications.py
git commit -m "feat: create notifications on follow and mutual follow"
```

---

### Task 7: Booking → Notification Integration

**Files:**
- Modify: `app/services/booking.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write failing integration tests for booking notifications**

Append to `tests/test_notifications.py`. These tests need helper functions to create a court and booking:

```python
from datetime import date, time, timedelta


async def _create_court(client: AsyncClient, token: str) -> str:
    """Create a court and return its id."""
    resp = await client.post(
        "/api/v1/courts",
        json={
            "name": "Test Court",
            "address": "123 Test St",
            "city": "Hong Kong",
            "court_type": "outdoor",
        },
        headers=_auth(token),
    )
    return resp.json()["id"]


async def _approve_court(session: AsyncSession, court_id: str):
    """Directly approve a court in the DB for testing."""
    from app.models.court import Court
    from sqlalchemy import select

    result = await session.execute(select(Court).where(Court.id == uuid.UUID(court_id)))
    court = result.scalar_one()
    court.is_approved = True
    await session.commit()


async def _create_booking(client: AsyncClient, token: str, court_id: str) -> str:
    """Create a booking and return its id."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": court_id,
            "match_type": "singles",
            "play_date": tomorrow,
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "2.0",
            "max_ntrp": "5.0",
            "gender_requirement": "any",
        },
        headers=_auth(token),
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_join_booking_notifies_creator(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c1")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j1")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    booking_notifs = [n for n in notifs if n["type"] == "booking_joined"]
    assert len(booking_notifs) == 1
    assert booking_notifs[0]["actor_id"] == uid2
    assert booking_notifs[0]["target_type"] == "booking"
    assert booking_notifs[0]["target_id"] == booking_id


@pytest.mark.asyncio
async def test_accept_participant_notifies_participant(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c2")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j2")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))

    # Accept participant
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    accept_notifs = [n for n in notifs if n["type"] == "booking_accepted"]
    assert len(accept_notifs) == 1
    assert accept_notifs[0]["actor_id"] == uid1


@pytest.mark.asyncio
async def test_reject_participant_notifies_participant(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c3")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j3")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))

    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "rejected"},
        headers=_auth(token1),
    )

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    reject_notifs = [n for n in notifs if n["type"] == "booking_rejected"]
    assert len(reject_notifs) == 1


@pytest.mark.asyncio
async def test_cancel_booking_notifies_participants(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c4")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j4")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )

    await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=_auth(token1))

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    cancel_notifs = [n for n in notifs if n["type"] == "booking_cancelled"]
    assert len(cancel_notifs) == 1
    assert cancel_notifs[0]["actor_id"] == uid1


@pytest.mark.asyncio
async def test_confirm_booking_notifies_participants(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c5")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j5")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )

    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    confirm_notifs = [n for n in notifs if n["type"] == "booking_confirmed"]
    assert len(confirm_notifs) == 1


@pytest.mark.asyncio
async def test_complete_booking_notifies_participants(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c6")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j6")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    # Patch play_date to past so complete is allowed
    from app.models.booking import Booking
    from sqlalchemy import select

    result = await session.execute(select(Booking).where(Booking.id == uuid.UUID(booking_id)))
    booking = result.scalar_one()
    booking.play_date = date.today() - timedelta(days=1)
    booking.start_time = time(10, 0)
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    complete_notifs = [n for n in notifs if n["type"] == "booking_completed"]
    assert len(complete_notifs) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_notifications.py::test_join_booking_notifies_creator -v
```

Expected: FAIL — no booking_joined notification found.

- [ ] **Step 3: Add notification calls to booking service**

In `app/services/booking.py`, add the import at the top:

```python
from app.models.notification import NotificationType
from app.services.notification import create_notification
```

**In `join_booking`**, after `session.add(participant)` and before `await session.commit()`:

```python
    # Notify booking creator
    await create_notification(
        session,
        recipient_id=booking.creator_id,
        type=NotificationType.BOOKING_JOINED,
        actor_id=user.id,
        target_type="booking",
        target_id=booking.id,
    )
```

**In `update_participant_status`**, after `p.status = ParticipantStatus(new_status)` and before `await session.commit()`:

```python
            # Notify participant of status change
            if new_status == "accepted":
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_ACCEPTED,
                    actor_id=booking.creator_id,
                    target_type="booking",
                    target_id=booking.id,
                )
            elif new_status == "rejected":
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_REJECTED,
                    actor_id=booking.creator_id,
                    target_type="booking",
                    target_id=booking.id,
                )
```

**In `cancel_booking`**, after `booking.status = BookingStatus.CANCELLED` (inside the `if user.id == booking.creator_id:` block), before `await apply_credit_change`:

```python
        # Notify all accepted/pending participants (except creator)
        for p in booking.participants:
            if p.user_id != user.id and p.status in (ParticipantStatus.PENDING, ParticipantStatus.ACCEPTED):
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_CANCELLED,
                    actor_id=user.id,
                    target_type="booking",
                    target_id=booking.id,
                )
```

**In `confirm_booking`**, after `booking.status = BookingStatus.CONFIRMED` and before `await session.commit()`:

```python
    # Notify all participants except creator
    for p in booking.participants:
        if p.user_id != booking.creator_id and p.status == ParticipantStatus.ACCEPTED:
            await create_notification(
                session,
                recipient_id=p.user_id,
                type=NotificationType.BOOKING_CONFIRMED,
                actor_id=booking.creator_id,
                target_type="booking",
                target_id=booking.id,
            )
```

**In `complete_booking`**, inside the `for p in booking.participants:` loop, after the `apply_credit_change` call, still inside `if p.status == ParticipantStatus.ACCEPTED:`:

```python
            if p.user_id != booking.creator_id:
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_COMPLETED,
                    actor_id=booking.creator_id,
                    target_type="booking",
                    target_id=booking.id,
                )
```

- [ ] **Step 4: Run booking notification tests**

Run:
```bash
uv run pytest tests/test_notifications.py -k "booking" -v
```

Expected: All booking notification tests PASS.

- [ ] **Step 5: Run all booking tests to check for regressions**

Run:
```bash
uv run pytest tests/test_bookings.py -v
```

Expected: All existing booking tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/booking.py tests/test_notifications.py
git commit -m "feat: create notifications on booking join/accept/reject/cancel/confirm/complete"
```

---

### Task 8: Review → Notification Integration

**Files:**
- Modify: `app/services/review.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write failing integration test for review reveal notification**

Append to `tests/test_notifications.py`:

```python
@pytest.mark.asyncio
async def test_review_revealed_notifies_both_users(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "rnotif_c1")
    token2, uid2 = await _register_and_get_token(client, "rnotif_j1")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    # Join, accept, confirm
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    # Set play_date to past and complete
    from app.models.booking import Booking
    from sqlalchemy import select

    result = await session.execute(select(Booking).where(Booking.id == uuid.UUID(booking_id)))
    booking = result.scalar_one()
    booking.play_date = date.today() - timedelta(days=1)
    booking.start_time = time(10, 0)
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    # User1 reviews User2 — no reveal yet
    await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 4,
        },
        headers=_auth(token1),
    )

    # Check no review_revealed notifications yet
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    reveal_notifs = [n for n in resp.json() if n["type"] == "review_revealed"]
    assert len(reveal_notifs) == 0

    # User2 reviews User1 — triggers reveal
    await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid1,
            "skill_rating": 3,
            "punctuality_rating": 4,
            "sportsmanship_rating": 5,
        },
        headers=_auth(token2),
    )

    # Both users should get review_revealed notification
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    reveal_notifs = [n for n in resp.json() if n["type"] == "review_revealed"]
    assert len(reveal_notifs) == 1
    assert reveal_notifs[0]["target_type"] == "review"

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    reveal_notifs = [n for n in resp.json() if n["type"] == "review_revealed"]
    assert len(reveal_notifs) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_notifications.py::test_review_revealed_notifies_both_users -v
```

Expected: FAIL — no review_revealed notifications.

- [ ] **Step 3: Add notification calls to review service**

In `app/services/review.py`, add the import:

```python
from app.models.notification import NotificationType
from app.services.notification import create_notification
```

In `submit_review`, after `is_revealed = reverse is not None`, add before the return:

```python
    if is_revealed:
        # Notify both users that reviews are now visible
        await create_notification(
            session,
            recipient_id=reviewer.id,
            type=NotificationType.REVIEW_REVEALED,
            target_type="review",
            target_id=review.id,
        )
        await create_notification(
            session,
            recipient_id=reviewee_id,
            type=NotificationType.REVIEW_REVEALED,
            target_type="review",
            target_id=reverse.id,
        )
        await session.commit()
```

Note: `submit_review` already calls `await session.commit()` earlier when creating the review. The reveal notifications need their own commit since they happen after the review is persisted. Alternatively, restructure to use flush + single commit. Let's use flush for the review and commit once at the end:

Replace the existing commit in `submit_review` (the line `await session.commit()` after `session.add(review)`) with `await session.flush()`, then add the notification + commit block:

```python
    session.add(review)
    await session.flush()
    await session.refresh(review)

    # Check if reverse review exists (is_revealed)
    reverse = await get_reverse_review(session, booking_id, reviewer.id, reviewee_id)
    is_revealed = reverse is not None

    if is_revealed:
        await create_notification(
            session,
            recipient_id=reviewer.id,
            type=NotificationType.REVIEW_REVEALED,
            target_type="review",
            target_id=review.id,
        )
        await create_notification(
            session,
            recipient_id=reviewee_id,
            type=NotificationType.REVIEW_REVEALED,
            target_type="review",
            target_id=reverse.id,
        )

    await session.commit()

    return review, is_revealed
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_notifications.py::test_review_revealed_notifies_both_users -v
```

Expected: PASS.

- [ ] **Step 5: Run all review tests for regressions**

Run:
```bash
uv run pytest tests/test_reviews.py -v
```

Expected: All existing review tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/review.py tests/test_notifications.py
git commit -m "feat: create notifications on review blind reveal"
```

---

### Task 9: Report Resolution → Notification Integration

**Files:**
- Modify: `app/services/report.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write failing integration tests for report resolution notifications**

Append to `tests/test_notifications.py`:

```python
from app.models.user import UserRole


async def _make_admin(session: AsyncSession, user_id: str):
    """Promote a user to admin in the DB."""
    from app.models.user import User
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one()
    user.role = UserRole.ADMIN
    await session.commit()


@pytest.mark.asyncio
async def test_report_resolved_notifies_reporter(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "repnotif1")
    token2, uid2 = await _register_and_get_token(client, "repnotif2")
    admin_token, admin_id = await _register_and_get_token(client, "repnotif_admin")
    await _make_admin(session, admin_id)

    # User1 reports User2
    resp = await client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": uid2,
            "target_type": "user",
            "reason": "harassment",
        },
        headers=_auth(token1),
    )
    report_id = resp.json()["id"]

    # Admin resolves as dismissed
    await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "dismissed"},
        headers=_auth(admin_token),
    )

    # Reporter should get report_resolved notification
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    resolved_notifs = [n for n in notifs if n["type"] == "report_resolved"]
    assert len(resolved_notifs) == 1
    assert resolved_notifs[0]["target_type"] == "report"
    assert resolved_notifs[0]["target_id"] == report_id


@pytest.mark.asyncio
async def test_report_warned_notifies_target(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "warnnotif1")
    token2, uid2 = await _register_and_get_token(client, "warnnotif2")
    admin_token, admin_id = await _register_and_get_token(client, "warnnotif_admin")
    await _make_admin(session, admin_id)

    resp = await client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": uid2,
            "target_type": "user",
            "reason": "harassment",
        },
        headers=_auth(token1),
    )
    report_id = resp.json()["id"]

    await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "warned"},
        headers=_auth(admin_token),
    )

    # Reported user should get account_warned notification
    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    warn_notifs = [n for n in notifs if n["type"] == "account_warned"]
    assert len(warn_notifs) == 1
    assert warn_notifs[0]["target_type"] == "report"


@pytest.mark.asyncio
async def test_report_suspended_notifies_target(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "suspnotif1")
    token2, uid2 = await _register_and_get_token(client, "suspnotif2")
    admin_token, admin_id = await _register_and_get_token(client, "suspnotif_admin")
    await _make_admin(session, admin_id)

    resp = await client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": uid2,
            "target_type": "user",
            "reason": "harassment",
        },
        headers=_auth(token1),
    )
    report_id = resp.json()["id"]

    await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "suspended"},
        headers=_auth(admin_token),
    )

    # Note: suspended user can't access endpoints, so we check DB directly
    from app.models.notification import Notification, NotificationType
    from sqlalchemy import select

    result = await session.execute(
        select(Notification).where(
            Notification.recipient_id == uuid.UUID(uid2),
            Notification.type == NotificationType.ACCOUNT_SUSPENDED,
        )
    )
    notif = result.scalar_one_or_none()
    assert notif is not None
    assert notif.target_type == "report"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_notifications.py::test_report_resolved_notifies_reporter -v
```

Expected: FAIL — no report_resolved notification.

- [ ] **Step 3: Add notification calls to report service**

In `app/services/report.py`, add the import:

```python
from app.models.notification import NotificationType
from app.services.notification import create_notification
```

In `resolve_report`, replace `await session.commit()` near the end with notification creation + commit. After `report.resolved_at = datetime.now(timezone.utc)` and before the existing `await session.commit()`:

```python
    # Notify reporter that report was resolved
    await create_notification(
        session,
        recipient_id=report.reporter_id,
        type=NotificationType.REPORT_RESOLVED,
        target_type="report",
        target_id=report.id,
    )

    # Notify target user of moderation action
    if res == ReportResolution.WARNED:
        await create_notification(
            session,
            recipient_id=report.reported_user_id,
            type=NotificationType.ACCOUNT_WARNED,
            target_type="report",
            target_id=report.id,
        )
    elif res == ReportResolution.SUSPENDED:
        await create_notification(
            session,
            recipient_id=report.reported_user_id,
            type=NotificationType.ACCOUNT_SUSPENDED,
            target_type="report",
            target_id=report.id,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_notifications.py -k "report" -v
```

Expected: All three report notification tests PASS.

- [ ] **Step 5: Run all report tests for regressions**

Run:
```bash
uv run pytest tests/test_reports.py -v
```

Expected: All existing report tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/report.py tests/test_notifications.py
git commit -m "feat: create notifications on report resolve/warn/suspend"
```

---

### Task 10: Full Test Suite and CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run all tests**

Run:
```bash
uv run pytest tests/ -v
```

Expected: All tests PASS with no regressions.

- [ ] **Step 2: Update CLAUDE.md**

Add the notification system to the "Key patterns" section in `CLAUDE.md`, after the Follow system entry:

```markdown
- **Notification system**: `services/notification.py` + `routers/notifications.py` — in-app notifications created by direct service calls at trigger points. Covers booking events, follow/mutual, review blind reveal, and admin report resolution. No push delivery; iOS client polls REST API. `NotificationType` enum defines all event types. `create_notification()` is internal-only (not exposed via router).
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with Phase 5 notification system"
```
