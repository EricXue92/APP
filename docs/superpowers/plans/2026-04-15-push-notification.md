# Push Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FCM push notification support for time-sensitive notifications (8 of 29 types), delivered asynchronously via a Redis-backed in-process worker.

**Architecture:** New `DeviceToken` model stores per-user FCM tokens. `create_notification()` enqueues push jobs to a Redis list for pushable types. An asyncio background task (started in app lifespan) consumes jobs, looks up device tokens, and sends via `firebase-admin` SDK. Chat messages only push when the user has no active WebSocket connection.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Redis, firebase-admin, pytest

---

## File Structure

### New files

| File                         | Responsibility                                                    |
| ---------------------------- | ----------------------------------------------------------------- |
| `app/models/device_token.py` | `DeviceToken` SQLAlchemy model                                    |
| `app/schemas/device.py`      | Request/response schemas for device endpoints                     |
| `app/services/device.py`     | Device token CRUD (register, remove, list)                        |
| `app/services/push.py`       | `PUSHABLE_TYPES`, `enqueue_push()`, `push_worker()`, `send_fcm()` |
| `app/routers/devices.py`     | `POST /api/v1/devices`, `DELETE /api/v1/devices/{token}`          |
| `tests/test_devices.py`      | Device token endpoint tests                                       |
| `tests/test_push.py`         | Push service unit tests                                           |

### Modified files

| File                           | Change                                                                                       |
| ------------------------------ | -------------------------------------------------------------------------------------------- |
| `app/models/__init__.py`       | Add `DeviceToken` import + export                                                            |
| `app/config.py`                | Add `firebase_credentials_path` setting                                                      |
| `app/i18n.py`                  | Add `push.*` i18n keys for 8 pushable types                                                  |
| `app/services/notification.py` | Add optional `redis` + `ws_manager` params to `create_notification()`; call `enqueue_push()` |
| `app/main.py`                  | Register devices router, start push worker in lifespan                                       |
| `tests/conftest.py`            | Add `DeviceToken` to model imports                                                           |

---

### Task 1: DeviceToken model + migration

**Files:**

- Create: `app/models/device_token.py`
- Modify: `app/models/__init__.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write test that uses the DeviceToken model**

Create `tests/test_devices.py`:

```python
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_token import DeviceToken


@pytest.mark.asyncio
async def test_create_device_token(session: AsyncSession):
    from app.models.user import User, Gender

    user = User(nickname="push_user", gender=Gender.MALE, city="Taipei", ntrp_level="3.5", ntrp_label="3.5")
    session.add(user)
    await session.flush()

    token = DeviceToken(user_id=user.id, platform="ios", token="fcm-token-abc123")
    session.add(token)
    await session.flush()

    result = await session.execute(select(DeviceToken).where(DeviceToken.user_id == user.id))
    saved = result.scalar_one()
    assert saved.platform == "ios"
    assert saved.token == "fcm-token-abc123"
    assert saved.id is not None
    assert saved.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_devices.py::test_create_device_token -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.device_token'`

- [ ] **Step 3: Create the DeviceToken model**

Create `app/models/device_token.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeviceToken(Base):
    __tablename__ = "device_tokens"
    __table_args__ = (UniqueConstraint("user_id", "token", name="uq_device_tokens_user_token"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(10))
    token: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: Add DeviceToken to models/**init**.py**

Add to `app/models/__init__.py`:

```python
from app.models.device_token import DeviceToken
```

And add `"DeviceToken"` to the `__all__` list.

- [ ] **Step 5: Add DeviceToken to conftest.py imports**

In `tests/conftest.py`, add `DeviceToken` to the model import line so the table is created during tests:

```python
from app.models import Booking, BookingParticipant, Block, Court, CreditLog, Follow, Notification, Report, Review, User, UserAuth, MatchPreference, MatchTimeSlot, MatchPreferenceCourt, MatchProposal, ChatRoom, ChatParticipant, Message, Event, EventParticipant, EventMatch, EventSet, AdminAuditLog, DeviceToken  # noqa: F401
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_devices.py::test_create_device_token -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/models/device_token.py app/models/__init__.py tests/conftest.py tests/test_devices.py
git commit -m "feat(push): add DeviceToken model"
```

---

### Task 2: Device token service (CRUD)

**Files:**

- Create: `app/services/device.py`
- Modify: `tests/test_devices.py`

- [ ] **Step 1: Write tests for device service**

Append to `tests/test_devices.py`:

```python
from app.services.device import register_device, remove_device, get_user_device_tokens


async def _create_user(session: AsyncSession, username: str) -> uuid.UUID:
    from app.models.user import User, Gender

    user = User(nickname=f"Player_{username}", gender=Gender.MALE, city="Taipei", ntrp_level="3.5", ntrp_label="3.5")
    session.add(user)
    await session.flush()
    return user.id


@pytest.mark.asyncio
async def test_register_device(session: AsyncSession):
    user_id = await _create_user(session, "dev_reg")
    dt = await register_device(session, user_id=user_id, platform="android", token="fcm-token-111")
    assert dt.user_id == user_id
    assert dt.platform == "android"
    assert dt.token == "fcm-token-111"


@pytest.mark.asyncio
async def test_register_device_duplicate_is_idempotent(session: AsyncSession):
    user_id = await _create_user(session, "dev_dup")
    dt1 = await register_device(session, user_id=user_id, platform="ios", token="fcm-dup-token")
    dt2 = await register_device(session, user_id=user_id, platform="ios", token="fcm-dup-token")
    assert dt1.id == dt2.id

    tokens = await get_user_device_tokens(session, user_id)
    assert len(tokens) == 1


@pytest.mark.asyncio
async def test_multiple_devices_per_user(session: AsyncSession):
    user_id = await _create_user(session, "dev_multi")
    await register_device(session, user_id=user_id, platform="ios", token="token-iphone")
    await register_device(session, user_id=user_id, platform="android", token="token-android")

    tokens = await get_user_device_tokens(session, user_id)
    assert len(tokens) == 2


@pytest.mark.asyncio
async def test_remove_device(session: AsyncSession):
    user_id = await _create_user(session, "dev_rm")
    await register_device(session, user_id=user_id, platform="ios", token="token-remove-me")
    await remove_device(session, user_id=user_id, token="token-remove-me")

    tokens = await get_user_device_tokens(session, user_id)
    assert len(tokens) == 0


@pytest.mark.asyncio
async def test_remove_device_not_found(session: AsyncSession):
    user_id = await _create_user(session, "dev_rm404")
    with pytest.raises(LookupError):
        await remove_device(session, user_id=user_id, token="nonexistent-token")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_devices.py -v -k "not test_create_device_token"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.device'`

- [ ] **Step 3: Implement device service**

Create `app/services/device.py`:

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_token import DeviceToken


async def register_device(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    platform: str,
    token: str,
) -> DeviceToken:
    result = await session.execute(
        select(DeviceToken).where(
            DeviceToken.user_id == user_id,
            DeviceToken.token == token,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    device_token = DeviceToken(user_id=user_id, platform=platform, token=token)
    session.add(device_token)
    await session.flush()
    return device_token


async def remove_device(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    token: str,
) -> None:
    result = await session.execute(
        select(DeviceToken).where(
            DeviceToken.user_id == user_id,
            DeviceToken.token == token,
        )
    )
    device_token = result.scalar_one_or_none()
    if device_token is None:
        raise LookupError("Device token not found")
    await session.delete(device_token)
    await session.flush()


async def get_user_device_tokens(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[DeviceToken]:
    result = await session.execute(
        select(DeviceToken).where(DeviceToken.user_id == user_id)
    )
    return list(result.scalars().all())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_devices.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/device.py tests/test_devices.py
git commit -m "feat(push): add device token CRUD service"
```

---

### Task 3: Device token router + schemas

**Files:**

- Create: `app/schemas/device.py`
- Create: `app/routers/devices.py`
- Modify: `app/main.py`
- Modify: `tests/test_devices.py`

- [ ] **Step 1: Write endpoint tests**

Append to `tests/test_devices.py`:

```python
from httpx import AsyncClient


async def _register_and_get_token(client: AsyncClient, username: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": "male",
            "city": "Taipei",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_register_device_endpoint(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "devapi_reg")
    resp = await client.post(
        "/api/v1/devices",
        json={"platform": "ios", "token": "fcm-endpoint-token"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["platform"] == "ios"
    assert data["token"] == "fcm-endpoint-token"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_device_duplicate_endpoint(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "devapi_dup")
    body = {"platform": "ios", "token": "fcm-dup-endpoint"}
    resp1 = await client.post("/api/v1/devices", json=body, headers=_auth(token))
    resp2 = await client.post("/api/v1/devices", json=body, headers=_auth(token))
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_delete_device_endpoint(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "devapi_del")
    await client.post(
        "/api/v1/devices",
        json={"platform": "android", "token": "fcm-delete-me"},
        headers=_auth(token),
    )
    resp = await client.delete("/api/v1/devices/fcm-delete-me", headers=_auth(token))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_device_not_found_endpoint(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "devapi_del404")
    resp = await client.delete("/api/v1/devices/nonexistent", headers=_auth(token))
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_devices.py -v -k "endpoint"`
Expected: FAIL — 404 (router not registered)

- [ ] **Step 3: Create device schemas**

Create `app/schemas/device.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DeviceTokenCreate(BaseModel):
    platform: str = Field(..., pattern="^(ios|android)$")
    token: str = Field(..., min_length=1, max_length=500)


class DeviceTokenResponse(BaseModel):
    id: uuid.UUID
    platform: str
    token: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Create devices router**

Create `app/routers/devices.py`:

```python
from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.device import DeviceTokenCreate, DeviceTokenResponse
from app.services.device import register_device, remove_device

router = APIRouter()


@router.post("", response_model=DeviceTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_device_token(body: DeviceTokenCreate, user: CurrentUser, session: DbSession):
    dt = await register_device(session, user_id=user.id, platform=body.platform, token=body.token)
    await session.commit()
    return dt


@router.delete("/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_token(token: str, user: CurrentUser, session: DbSession):
    try:
        await remove_device(session, user_id=user.id, token=token)
        await session.commit()
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device token not found")
```

- [ ] **Step 5: Register router in main.py**

In `app/main.py`, add to the imports:

```python
from app.routers import auth, assistant, blocks, bookings, chat, courts, devices, events, follows, matching, notifications, reports, reviews, users, weather
```

And add after the existing router registrations:

```python
app.include_router(devices.router, prefix="/api/v1/devices", tags=["devices"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_devices.py -v`
Expected: all 10 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/schemas/device.py app/routers/devices.py app/main.py tests/test_devices.py
git commit -m "feat(push): add device token REST endpoints"
```

---

### Task 4: Push i18n keys

**Files:**

- Modify: `app/i18n.py`
- Create: `tests/test_push.py`

- [ ] **Step 1: Write test for push i18n keys**

Create `tests/test_push.py`:

```python
import pytest

from app.i18n import t


PUSH_TYPES = [
    "booking_confirmed",
    "booking_cancelled",
    "match_proposal_received",
    "event_match_ready",
    "event_score_submitted",
    "event_score_disputed",
    "account_suspended",
    "new_chat_message",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("ntype", PUSH_TYPES)
async def test_push_i18n_title_exists(ntype: str):
    for lang in ("zh-Hant", "zh-Hans", "en"):
        key = f"push.{ntype}.title"
        result = t(key, lang)
        assert result != key, f"Missing i18n key: {key} for lang={lang}"


@pytest.mark.asyncio
@pytest.mark.parametrize("ntype", PUSH_TYPES)
async def test_push_i18n_body_exists(ntype: str):
    for lang in ("zh-Hant", "zh-Hans", "en"):
        key = f"push.{ntype}.body"
        result = t(key, lang)
        assert result != key, f"Missing i18n key: {key} for lang={lang}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_push.py -v -k "i18n"`
Expected: FAIL — keys fall back to key name

- [ ] **Step 3: Add push i18n keys to i18n.py**

Add the following entries to the `_MESSAGES` dict in `app/i18n.py`, before the closing `}`:

```python
    # Push notification messages
    "push.booking_confirmed.title": {
        "zh-Hant": "訂場已確認",
        "zh-Hans": "订场已确认",
        "en": "Booking Confirmed",
    },
    "push.booking_confirmed.body": {
        "zh-Hant": "您的訂場已確認，請準時參加",
        "zh-Hans": "您的订场已确认，请准时参加",
        "en": "Your booking has been confirmed",
    },
    "push.booking_cancelled.title": {
        "zh-Hant": "訂場已取消",
        "zh-Hans": "订场已取消",
        "en": "Booking Cancelled",
    },
    "push.booking_cancelled.body": {
        "zh-Hant": "您參加的訂場已被取消",
        "zh-Hans": "您参加的订场已被取消",
        "en": "A booking you joined has been cancelled",
    },
    "push.match_proposal_received.title": {
        "zh-Hant": "收到配對邀請",
        "zh-Hans": "收到配对邀请",
        "en": "Match Proposal Received",
    },
    "push.match_proposal_received.body": {
        "zh-Hant": "有人邀請您一起打球",
        "zh-Hans": "有人邀请您一起打球",
        "en": "Someone wants to play tennis with you",
    },
    "push.event_match_ready.title": {
        "zh-Hant": "賽事對戰已就緒",
        "zh-Hans": "赛事对战已就绪",
        "en": "Event Match Ready",
    },
    "push.event_match_ready.body": {
        "zh-Hant": "您的下一場比賽已準備就緒",
        "zh-Hans": "您的下一场比赛已准备就绪",
        "en": "Your next match is ready",
    },
    "push.event_score_submitted.title": {
        "zh-Hant": "比分已提交",
        "zh-Hans": "比分已提交",
        "en": "Score Submitted",
    },
    "push.event_score_submitted.body": {
        "zh-Hant": "對手已提交比分，請確認",
        "zh-Hans": "对手已提交比分，请确认",
        "en": "Your opponent submitted a score, please confirm",
    },
    "push.event_score_disputed.title": {
        "zh-Hant": "比分有爭議",
        "zh-Hans": "比分有争议",
        "en": "Score Disputed",
    },
    "push.event_score_disputed.body": {
        "zh-Hant": "比分確認出現爭議，請聯繫管理員",
        "zh-Hans": "比分确认出现争议，请联系管理员",
        "en": "A score dispute needs attention",
    },
    "push.account_suspended.title": {
        "zh-Hant": "帳號已被停權",
        "zh-Hans": "账号已被停权",
        "en": "Account Suspended",
    },
    "push.account_suspended.body": {
        "zh-Hant": "您的帳號已被管理員停權",
        "zh-Hans": "您的账号已被管理员停权",
        "en": "Your account has been suspended by an administrator",
    },
    "push.new_chat_message.title": {
        "zh-Hant": "新訊息",
        "zh-Hans": "新消息",
        "en": "New Message",
    },
    "push.new_chat_message.body": {
        "zh-Hant": "您收到一條新訊息",
        "zh-Hans": "您收到一条新消息",
        "en": "You have a new message",
    },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_push.py -v -k "i18n"`
Expected: all 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/i18n.py tests/test_push.py
git commit -m "feat(push): add i18n keys for push notification messages"
```

---

### Task 5: Firebase config + push service

**Files:**

- Modify: `app/config.py`
- Create: `app/services/push.py`
- Modify: `tests/test_push.py`

- [ ] **Step 1: Add firebase config setting**

In `app/config.py`, add to the `Settings` class after the QWeather settings:

```python
    # Push notifications (FCM)
    firebase_credentials_path: str = ""
```

- [ ] **Step 2: Write tests for enqueue_push**

Append to `tests/test_push.py`:

```python
import json
import uuid

from unittest.mock import AsyncMock, MagicMock

from app.models.notification import Notification, NotificationType
from app.services.push import PUSHABLE_TYPES, enqueue_push


def _make_notification(
    type: NotificationType,
    recipient_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
) -> Notification:
    n = Notification(
        id=uuid.uuid4(),
        recipient_id=recipient_id or uuid.uuid4(),
        actor_id=actor_id,
        type=type,
        target_type=target_type,
        target_id=target_id,
    )
    return n


@pytest.mark.asyncio
async def test_enqueue_push_pushable_type():
    redis = AsyncMock()
    notification = _make_notification(NotificationType.BOOKING_CONFIRMED, target_type="booking", target_id=uuid.uuid4())
    result = await enqueue_push(redis, notification)
    assert result is True
    redis.lpush.assert_called_once()
    payload = json.loads(redis.lpush.call_args[0][1])
    assert payload["type"] == "booking_confirmed"


@pytest.mark.asyncio
async def test_enqueue_push_non_pushable_type():
    redis = AsyncMock()
    notification = _make_notification(NotificationType.NEW_FOLLOWER)
    result = await enqueue_push(redis, notification)
    assert result is False
    redis.lpush.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_push_chat_skips_when_online():
    redis = AsyncMock()
    recipient_id = uuid.uuid4()
    notification = _make_notification(NotificationType.NEW_CHAT_MESSAGE, recipient_id=recipient_id)

    ws_manager = MagicMock()
    ws_manager.connections = {recipient_id: MagicMock()}

    result = await enqueue_push(redis, notification, ws_manager=ws_manager)
    assert result is False
    redis.lpush.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_push_chat_sends_when_offline():
    redis = AsyncMock()
    recipient_id = uuid.uuid4()
    notification = _make_notification(NotificationType.NEW_CHAT_MESSAGE, recipient_id=recipient_id)

    ws_manager = MagicMock()
    ws_manager.connections = {}

    result = await enqueue_push(redis, notification, ws_manager=ws_manager)
    assert result is True
    redis.lpush.assert_called_once()


@pytest.mark.asyncio
async def test_enqueue_push_chat_sends_when_no_manager():
    redis = AsyncMock()
    notification = _make_notification(NotificationType.NEW_CHAT_MESSAGE)
    result = await enqueue_push(redis, notification, ws_manager=None)
    assert result is True
    redis.lpush.assert_called_once()


@pytest.mark.asyncio
async def test_pushable_types_count():
    assert len(PUSHABLE_TYPES) == 8
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_push.py -v -k "enqueue"`
Expected: FAIL — `ImportError: cannot import name 'enqueue_push' from 'app.services.push'`

- [ ] **Step 4: Implement push service**

Create `app/services/push.py`:

```python
from __future__ import annotations

import json
import logging
import uuid

from redis.asyncio import Redis

from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)

PUSHABLE_TYPES: set[NotificationType] = {
    NotificationType.BOOKING_CONFIRMED,
    NotificationType.BOOKING_CANCELLED,
    NotificationType.MATCH_PROPOSAL_RECEIVED,
    NotificationType.EVENT_MATCH_READY,
    NotificationType.EVENT_SCORE_SUBMITTED,
    NotificationType.EVENT_SCORE_DISPUTED,
    NotificationType.ACCOUNT_SUSPENDED,
    NotificationType.NEW_CHAT_MESSAGE,
}

PUSH_QUEUE_KEY = "push:queue"


async def enqueue_push(
    redis: Redis,
    notification: Notification,
    *,
    ws_manager=None,
) -> bool:
    if notification.type not in PUSHABLE_TYPES:
        return False

    if notification.type == NotificationType.NEW_CHAT_MESSAGE and ws_manager is not None:
        if notification.recipient_id in ws_manager.connections:
            return False

    payload = json.dumps({
        "notification_id": str(notification.id),
        "recipient_id": str(notification.recipient_id),
        "type": notification.type.value,
        "actor_id": str(notification.actor_id) if notification.actor_id else None,
        "target_type": notification.target_type,
        "target_id": str(notification.target_id) if notification.target_id else None,
    })

    await redis.lpush(PUSH_QUEUE_KEY, payload)
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_push.py -v`
Expected: all 22 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/services/push.py tests/test_push.py
git commit -m "feat(push): add push enqueue service with PUSHABLE_TYPES"
```

---

### Task 6: Push worker (consumer + FCM sender)

**Files:**

- Modify: `app/services/push.py`
- Modify: `tests/test_push.py`

- [ ] **Step 1: Write tests for send_fcm and build_push_message**

Append to `tests/test_push.py`:

```python
from app.services.push import build_push_message, send_fcm


@pytest.mark.asyncio
async def test_build_push_message_en():
    title, body = build_push_message("booking_confirmed", "en")
    assert title == "Booking Confirmed"
    assert "confirmed" in body.lower()


@pytest.mark.asyncio
async def test_build_push_message_zh_hant():
    title, body = build_push_message("booking_confirmed", "zh-Hant")
    assert "確認" in title


@pytest.mark.asyncio
async def test_build_push_message_all_types():
    for ntype in PUSH_TYPES:
        title, body = build_push_message(ntype, "en")
        assert len(title) > 0
        assert len(body) > 0


@pytest.mark.asyncio
async def test_send_fcm_returns_stale_tokens(monkeypatch):
    from unittest.mock import patch, MagicMock
    import firebase_admin.messaging as fcm_module

    mock_response = MagicMock()
    mock_response.responses = [
        MagicMock(success=True, exception=None),
        MagicMock(success=False, exception=MagicMock(code="UNREGISTERED")),
        MagicMock(success=False, exception=MagicMock(code="INTERNAL")),
    ]

    with patch.object(fcm_module, "send_each_for_multicast", return_value=mock_response):
        stale = await send_fcm(
            tokens=["good-token", "stale-token", "error-token"],
            title="Test",
            body="Test body",
            data={"type": "booking_confirmed"},
        )

    assert stale == ["stale-token"]


@pytest.mark.asyncio
async def test_send_fcm_empty_tokens():
    stale = await send_fcm(tokens=[], title="Test", body="Body", data={})
    assert stale == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_push.py -v -k "build_push_message or send_fcm"`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement build_push_message and send_fcm**

Append to `app/services/push.py`:

```python
import firebase_admin
from firebase_admin import credentials, messaging

from app.config import settings
from app.i18n import t


def _init_firebase() -> bool:
    if firebase_admin._apps:
        return True
    if not settings.firebase_credentials_path:
        logger.warning("firebase_credentials_path not set, push disabled")
        return False
    cred = credentials.Certificate(settings.firebase_credentials_path)
    firebase_admin.initialize_app(cred)
    return True


def build_push_message(notification_type: str, lang: str) -> tuple[str, str]:
    title = t(f"push.{notification_type}.title", lang)
    body = t(f"push.{notification_type}.body", lang)
    return title, body


async def send_fcm(
    *,
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str],
) -> list[str]:
    if not tokens:
        return []

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data,
        tokens=tokens,
    )

    response = messaging.send_each_for_multicast(message)

    stale_tokens: list[str] = []
    for i, send_response in enumerate(response.responses):
        if not send_response.success and send_response.exception:
            if getattr(send_response.exception, "code", "") == "UNREGISTERED":
                stale_tokens.append(tokens[i])
            else:
                logger.error("FCM send failed for token %s: %s", tokens[i], send_response.exception)

    return stale_tokens
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_push.py -v`
Expected: all 28 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/push.py tests/test_push.py
git commit -m "feat(push): add FCM sender and message builder"
```

---

### Task 7: Push worker loop + lifespan integration

**Files:**

- Modify: `app/services/push.py`
- Modify: `app/main.py`
- Modify: `tests/test_push.py`

- [ ] **Step 1: Write test for push_worker processing a job**

Append to `tests/test_push.py`:

```python
from app.services.push import process_push_job


@pytest.mark.asyncio
async def test_process_push_job_sends_fcm(monkeypatch):
    from unittest.mock import patch, AsyncMock as AioMock
    from app.models.user import User, Gender
    from app.models.device_token import DeviceToken
    from sqlalchemy.ext.asyncio import AsyncSession as RealSession

    job_data = {
        "notification_id": str(uuid.uuid4()),
        "recipient_id": str(uuid.uuid4()),
        "type": "booking_confirmed",
        "actor_id": None,
        "target_type": "booking",
        "target_id": str(uuid.uuid4()),
    }

    mock_session_factory = MagicMock()
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    # Mock get_user_device_tokens to return tokens
    mock_device = MagicMock()
    mock_device.token = "fcm-test-token"

    mock_user = MagicMock()
    mock_user.language = "en"

    with patch("app.services.push.get_user_device_tokens", new_callable=AioMock, return_value=[mock_device]) as mock_get_tokens, \
         patch("app.services.push.get_user_language", new_callable=AioMock, return_value="en") as mock_get_lang, \
         patch("app.services.push.send_fcm", new_callable=AioMock, return_value=[]) as mock_send, \
         patch("app.services.push._init_firebase", return_value=True):
        await process_push_job(mock_session_factory, job_data)

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args[1]
    assert call_kwargs["tokens"] == ["fcm-test-token"]
    assert call_kwargs["title"] == "Booking Confirmed"
    assert call_kwargs["data"]["type"] == "booking_confirmed"


@pytest.mark.asyncio
async def test_process_push_job_no_devices(monkeypatch):
    from unittest.mock import patch, AsyncMock as AioMock

    job_data = {
        "notification_id": str(uuid.uuid4()),
        "recipient_id": str(uuid.uuid4()),
        "type": "booking_confirmed",
        "actor_id": None,
        "target_type": "booking",
        "target_id": str(uuid.uuid4()),
    }

    mock_session_factory = MagicMock()
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.push.get_user_device_tokens", new_callable=AioMock, return_value=[]) as mock_get_tokens, \
         patch("app.services.push.get_user_language", new_callable=AioMock, return_value="en"), \
         patch("app.services.push.send_fcm", new_callable=AioMock) as mock_send, \
         patch("app.services.push._init_firebase", return_value=True):
        await process_push_job(mock_session_factory, job_data)

    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_process_push_job_removes_stale_tokens(monkeypatch):
    from unittest.mock import patch, AsyncMock as AioMock

    job_data = {
        "notification_id": str(uuid.uuid4()),
        "recipient_id": str(uuid.uuid4()),
        "type": "booking_cancelled",
        "actor_id": None,
        "target_type": "booking",
        "target_id": str(uuid.uuid4()),
    }

    mock_session_factory = MagicMock()
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_device = MagicMock()
    mock_device.token = "stale-token"

    with patch("app.services.push.get_user_device_tokens", new_callable=AioMock, return_value=[mock_device]), \
         patch("app.services.push.get_user_language", new_callable=AioMock, return_value="zh-Hant"), \
         patch("app.services.push.send_fcm", new_callable=AioMock, return_value=["stale-token"]) as mock_send, \
         patch("app.services.push.remove_stale_tokens", new_callable=AioMock) as mock_remove, \
         patch("app.services.push._init_firebase", return_value=True):
        await process_push_job(mock_session_factory, job_data)

    mock_remove.assert_called_once_with(mock_session, uuid.UUID(job_data["recipient_id"]), ["stale-token"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_push.py -v -k "process_push_job"`
Expected: FAIL — `ImportError: cannot import name 'process_push_job'`

- [ ] **Step 3: Implement process_push_job, get_user_language, remove_stale_tokens, push_worker**

Append to `app/services/push.py`:

```python
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.device_token import DeviceToken
from app.models.user import User
from app.services.device import get_user_device_tokens


async def get_user_language(session: AsyncSession, user_id: uuid.UUID) -> str:
    result = await session.execute(
        sa_select(User.language).where(User.id == user_id)
    )
    lang = result.scalar_one_or_none()
    return lang or settings.default_language


async def remove_stale_tokens(session: AsyncSession, user_id: uuid.UUID, stale_tokens: list[str]) -> None:
    for token_str in stale_tokens:
        result = await session.execute(
            sa_select(DeviceToken).where(
                DeviceToken.user_id == user_id,
                DeviceToken.token == token_str,
            )
        )
        dt = result.scalar_one_or_none()
        if dt:
            await session.delete(dt)
    await session.flush()


async def process_push_job(session_factory: async_sessionmaker, job_data: dict) -> None:
    if not _init_firebase():
        return

    recipient_id = uuid.UUID(job_data["recipient_id"])
    notification_type = job_data["type"]

    async with session_factory() as session:
        lang = await get_user_language(session, recipient_id)
        devices = await get_user_device_tokens(session, recipient_id)

        if not devices:
            return

        title, body = build_push_message(notification_type, lang)
        tokens = [d.token for d in devices]
        data = {
            "type": notification_type,
            "target_type": job_data.get("target_type") or "",
            "target_id": job_data.get("target_id") or "",
        }

        stale = await send_fcm(tokens=tokens, title=title, body=body, data=data)

        if stale:
            await remove_stale_tokens(session, recipient_id, stale)
            await session.commit()


async def push_worker(session_factory: async_sessionmaker, redis: Redis) -> None:
    logger.info("Push worker started")
    while True:
        try:
            result = await redis.brpop(PUSH_QUEUE_KEY, timeout=5)
            if result is None:
                continue
            _, raw = result
            job_data = json.loads(raw)
            await process_push_job(session_factory, job_data)
        except Exception:
            logger.exception("Push worker error")
```

- [ ] **Step 4: Update app/main.py lifespan to start push worker**

Replace the lifespan in `app/main.py`:

```python
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import async_session
from app.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.push import push_worker

    task = asyncio.create_task(push_worker(async_session, redis_client))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await redis_client.aclose()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_push.py -v`
Expected: all 31 tests PASS

- [ ] **Step 6: Run full test suite to check nothing is broken**

Run: `uv run pytest tests/ -v --tb=short`
Expected: all tests PASS (existing tests should be unaffected by lifespan change since test client creates its own app)

- [ ] **Step 7: Commit**

```bash
git add app/services/push.py app/main.py tests/test_push.py
git commit -m "feat(push): add push worker with FCM delivery and stale token cleanup"
```

---

### Task 8: Integrate push into create_notification

**Files:**

- Modify: `app/services/notification.py`
- Modify: `tests/test_push.py`

- [ ] **Step 1: Write integration test for create_notification triggering push**

Append to `tests/test_push.py`:

```python
from app.services.notification import create_notification
from app.models.notification import NotificationType
from redis.asyncio import Redis as AsyncRedis


@pytest.mark.asyncio
async def test_create_notification_enqueues_push_for_pushable_type(session, monkeypatch):
    from app.models.user import User, Gender

    user = User(nickname="push_int", gender=Gender.MALE, city="Taipei", ntrp_level="3.5", ntrp_label="3.5")
    session.add(user)
    await session.flush()

    mock_redis = AsyncMock()
    notification = await create_notification(
        session,
        recipient_id=user.id,
        type=NotificationType.BOOKING_CONFIRMED,
        target_type="booking",
        target_id=uuid.uuid4(),
        redis=mock_redis,
    )
    mock_redis.lpush.assert_called_once()


@pytest.mark.asyncio
async def test_create_notification_skips_push_for_non_pushable(session, monkeypatch):
    from app.models.user import User, Gender

    user = User(nickname="push_skip", gender=Gender.MALE, city="Taipei", ntrp_level="3.5", ntrp_label="3.5")
    session.add(user)
    await session.flush()

    mock_redis = AsyncMock()
    notification = await create_notification(
        session,
        recipient_id=user.id,
        type=NotificationType.NEW_FOLLOWER,
        redis=mock_redis,
    )
    mock_redis.lpush.assert_not_called()


@pytest.mark.asyncio
async def test_create_notification_works_without_redis(session, monkeypatch):
    """Backward compatibility: create_notification still works without redis param."""
    from app.models.user import User, Gender

    user = User(nickname="push_compat", gender=Gender.MALE, city="Taipei", ntrp_level="3.5", ntrp_label="3.5")
    session.add(user)
    await session.flush()

    notification = await create_notification(
        session,
        recipient_id=user.id,
        type=NotificationType.BOOKING_CONFIRMED,
        target_type="booking",
        target_id=uuid.uuid4(),
    )
    assert notification.id is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_push.py -v -k "create_notification"`
Expected: FAIL — `create_notification() got an unexpected keyword argument 'redis'`

- [ ] **Step 3: Update create_notification to support push enqueue**

Replace `app/services/notification.py`:

```python
import uuid

from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.services.push import enqueue_push


async def create_notification(
    session: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    type: NotificationType,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    redis: Redis | None = None,
    ws_manager=None,
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

    if redis is not None:
        await enqueue_push(redis, notification, ws_manager=ws_manager)

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_push.py -v`
Expected: all 34 tests PASS

- [ ] **Step 5: Run full test suite to verify backward compatibility**

Run: `uv run pytest tests/ -v --tb=short`
Expected: all tests PASS — existing callers of `create_notification()` don't pass `redis`, so they work unchanged.

- [ ] **Step 6: Commit**

```bash
git add app/services/notification.py tests/test_push.py
git commit -m "feat(push): integrate push enqueue into create_notification"
```

---

### Task 9: Alembic migration

**Files:**

- Generate: `alembic/versions/<auto>_add_device_tokens_table.py`

- [ ] **Step 1: Generate migration**

Run:

```bash
uv run alembic revision --autogenerate -m "add device_tokens table"
```

- [ ] **Step 2: Review the generated migration**

Verify it creates the `device_tokens` table with columns: `id`, `user_id`, `platform`, `token`, `created_at`, `updated_at`, and the unique constraint `uq_device_tokens_user_token`.

- [ ] **Step 3: Apply migration**

Run:

```bash
uv run alembic upgrade head
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add alembic/
git commit -m "migration: add device_tokens table for push notifications"
```

---

### Task 10: Final integration verification

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: all tests PASS (original 422 + new push/device tests)

- [ ] **Step 2: Verify server starts cleanly**

Run: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`

Check that:

- Server starts without errors
- Push worker log line appears: "Push worker started"
- Health endpoint responds: `curl http://localhost:8000/health`
- Device endpoints appear in docs: `http://localhost:8000/docs`

Stop the server with Ctrl+C.

- [ ] **Step 3: Verify no import cycles or missing dependencies**

Run:

```bash
uv run python -c "from app.services.push import enqueue_push, push_worker, send_fcm, process_push_job, build_push_message, PUSHABLE_TYPES; print('All push imports OK')"
uv run python -c "from app.services.device import register_device, remove_device, get_user_device_tokens; print('All device imports OK')"
```

- [ ] **Step 4: Commit any final fixes if needed**
