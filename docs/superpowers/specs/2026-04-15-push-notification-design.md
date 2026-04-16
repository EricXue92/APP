# Push Notification Design Spec

**Date:** 2026-04-15
**Status:** Approved
**Scope:** FCM push for iOS + Android native apps. WeChat 订阅消息 deferred to a future phase.

---

## Overview

Add push notification support to Let's Tennis. Currently all 29 notification types are in-app only (DB write + polling). This design adds real-time push delivery for time-sensitive notifications via Firebase Cloud Messaging (FCM), with async delivery through a Redis-backed background worker.

## Decisions

| Decision              | Choice                  | Rationale                                                                                 |
| --------------------- | ----------------------- | ----------------------------------------------------------------------------------------- |
| Push service          | FCM                     | One API for iOS + Android; wraps APNs for iOS. Works well in zh-Hant markets (Taiwan/HK). |
| Which types push      | 8 of 29                 | Only time-sensitive, action-required types. Avoids notification fatigue.                  |
| Chat push             | Only when offline       | Check WebSocket `ConnectionManager`; skip if user has active connection.                  |
| Delivery model        | Async via Redis queue   | External HTTP calls are slow/flaky; don't block user requests. Redis already available.   |
| Worker model          | In-process asyncio task | No extra processes to deploy. Can upgrade to ARQ worker later using same Redis interface. |
| User push preferences | Push all pushable types | Keep it simple for v1. Granular controls can be added later.                              |
| WeChat 订阅消息       | Deferred                | Different API model, requires template approval. Build FCM first, add WeChat later.       |

## Pushable Notification Types

```python
PUSHABLE_TYPES = {
    NotificationType.BOOKING_CONFIRMED,
    NotificationType.BOOKING_CANCELLED,
    NotificationType.MATCH_PROPOSAL_RECEIVED,
    NotificationType.EVENT_MATCH_READY,
    NotificationType.EVENT_SCORE_SUBMITTED,
    NotificationType.EVENT_SCORE_DISPUTED,
    NotificationType.ACCOUNT_SUSPENDED,
    NotificationType.NEW_CHAT_MESSAGE,  # only when user has no active WebSocket
}
```

All other notification types remain in-app only.

## Data Model

### New model: `DeviceToken`

```python
class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: UUID (PK, default uuid4)
    user_id: UUID (FK → users.id, ondelete CASCADE)
    platform: Enum("ios", "android")
    token: String (FCM registration token)
    created_at: DateTime (server_default now())
    updated_at: DateTime (server_default now(), onupdate now())
```

**Constraints:**

- Unique on `(user_id, token)` — prevents duplicate registrations
- One user can have multiple devices

### New endpoints

| Method   | Path                      | Purpose                                     |
| -------- | ------------------------- | ------------------------------------------- |
| `POST`   | `/api/v1/devices`         | Register device token (on login/app launch) |
| `DELETE` | `/api/v1/devices/{token}` | Remove device token (on logout)             |

**Request body for POST:**

```json
{
  "platform": "ios",
  "token": "fcm-registration-token-string"
}
```

## Architecture

### Push flow

```
Service calls create_notification()
    ↓
DB write (unchanged)
    ↓
Is type in PUSHABLE_TYPES?
    ├─ No → done
    └─ Yes → Is type NEW_CHAT_MESSAGE?
                ├─ Yes → Is user connected via WebSocket?
                │          ├─ Yes → done (skip push)
                │          └─ No → enqueue to Redis
                └─ No → enqueue to Redis
                            ↓
              push_worker (asyncio background task)
                            ↓
              BLPOP from push:queue
                            ↓
              Lookup recipient's DeviceTokens
                            ↓
              Build localized title/body via t()
                            ↓
              firebase_admin.messaging.send_each_for_multicast()
                            ↓
              Remove stale tokens (UNREGISTERED)
```

### Redis message format

Key: `push:queue` (Redis list)

```json
{
  "notification_id": "uuid",
  "recipient_id": "uuid",
  "type": "booking_confirmed",
  "actor_id": "uuid|null",
  "target_type": "booking",
  "target_id": "uuid"
}
```

## File Structure

### New files

| File                         | Responsibility                                   |
| ---------------------------- | ------------------------------------------------ |
| `app/models/device_token.py` | `DeviceToken` SQLAlchemy model                   |
| `app/schemas/device.py`      | Request/response schemas for device endpoints    |
| `app/services/device.py`     | Device token CRUD                                |
| `app/services/push.py`       | Push queue producer, consumer worker, FCM sender |
| `app/routers/devices.py`     | Register/remove device token endpoints           |
| `tests/test_push.py`         | Push service unit tests                          |
| `tests/test_devices.py`      | Device token endpoint tests                      |

### Modified files

| File                           | Change                                                                                                                            |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `app/services/notification.py` | Add optional `redis` and `ws_manager` params to `create_notification()`; call `enqueue_push()` after DB write if type is pushable |
| `app/main.py`                  | Start push worker in lifespan, register `/api/v1/devices` router                                                                  |
| `app/config.py`                | Add `firebase_credentials_path: str = ""` setting                                                                                 |
| `app/i18n.py`                  | Add `push.*` i18n keys for 8 pushable types                                                                                       |
| `app/database.py`              | Import `DeviceToken` so Alembic detects it                                                                                        |
| `tests/test_cross_module.py`   | Add push integration tests                                                                                                        |

## Push Message Content

### i18n keys

Each pushable type gets a `push.<type>.title` and `push.<type>.body` key:

```python
"push.booking_confirmed.title": {
    "zh-Hant": "訂場已確認",
    "zh-Hans": "订场已确认",
    "en": "Booking Confirmed",
},
"push.booking_confirmed.body": {
    "zh-Hant": "您的訂場已確認，請準時參加",
    "zh-Hans": "您的订场已确认，请准时参加",
    "en": "Your booking has been confirmed. See you on the court!",
},
# ... one pair per PUSHABLE_TYPE
```

### Message building

- **title**: `t(f"push.{type.value}.title", lang)` — short, type-based
- **body**: `t(f"push.{type.value}.body", lang)` — contextual detail
- **data payload**: `{ "type": "<type>", "target_type": "<target_type>", "target_id": "<uuid>" }` — for client-side deep linking
- **Language**: read from `User.language`, fallback to `settings.default_language`

## Service Layer

### `push.py` key functions

```python
PUSHABLE_TYPES: set[NotificationType]  # the 8 types listed above

async def enqueue_push(
    redis: Redis,
    notification: Notification,
    ws_manager: ConnectionManager | None = None,
) -> bool:
    """Enqueue a push job if the notification type is pushable.
    For NEW_CHAT_MESSAGE, checks WebSocket connection first.
    Returns True if enqueued, False if skipped."""

async def push_worker(app: FastAPI) -> None:
    """Long-running asyncio task. BLPOP from push:queue,
    look up device tokens, send FCM, clean stale tokens."""

async def send_fcm(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str],
) -> list[str]:
    """Send multicast FCM message. Returns list of stale tokens to remove."""
```

### `device.py` key functions

```python
async def register_device(
    session: AsyncSession,
    user_id: UUID,
    platform: str,
    token: str,
) -> DeviceToken:
    """Register or update device token. Idempotent on (user_id, token)."""

async def remove_device(
    session: AsyncSession,
    user_id: UUID,
    token: str,
) -> None:
    """Remove device token. Raises LookupError if not found."""

async def get_user_device_tokens(
    session: AsyncSession,
    user_id: UUID,
) -> list[DeviceToken]:
    """Get all device tokens for a user."""
```

## Testing Strategy

### `tests/test_push.py` — Push service unit tests

- `enqueue_push()` enqueues for pushable types, skips non-pushable
- `enqueue_push()` skips `NEW_CHAT_MESSAGE` when user has active WebSocket
- `enqueue_push()` enqueues `NEW_CHAT_MESSAGE` when user is offline
- Push message localization for each language (zh-Hant, zh-Hans, en)
- Stale token cleanup on `UNREGISTERED` response

### `tests/test_devices.py` — Device token endpoint tests

- Register device token (POST 201)
- Register duplicate token (idempotent, no error)
- Remove device token (DELETE 204)
- Remove non-existent token (404)
- Multiple devices per user

### `tests/test_cross_module.py` — Integration tests

- Booking confirmed → push job enqueued in Redis
- Chat message to offline user → push job enqueued
- Chat message to online user → no push job

### Mocking strategy

- **Mock**: `firebase_admin.messaging` — external service boundary
- **Real**: Redis — already available via `settings.redis_url`
- **Real**: PostgreSQL — existing `lets_tennis_test` database

## Configuration

New settings in `app/config.py`:

```python
firebase_credentials_path: str = ""  # path to Firebase service account JSON
```

New `.env` entry:

```
FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json
```

## Future Considerations (Out of Scope)

- WeChat 订阅消息 — add as second push provider via same `enqueue_push()` interface
- Per-type push preferences — add `PushPreference` model, check before enqueue
- Retry with backoff — upgrade to ARQ worker for retry semantics
- Push analytics — track delivery/open rates
- Badge count — include unread count in push payload
