# Phase 5 — Notification System Design Spec

## Overview

In-app notification system that informs users about events across the platform — bookings, follows, reviews, and moderation actions. Notifications are stored in the database and served via REST API. The iOS client polls for notifications and renders localized strings client-side based on the notification `type` enum. Push delivery (APNs) is deferred to a future phase.

## Data Model

### Notification table

```
notifications
├── id: UUID (PK, default uuid4)
├── recipient_id: UUID (FK → users.id, ON DELETE CASCADE)
├── actor_id: UUID | None (FK → users.id, ON DELETE SET NULL)
├── type: NotificationType (enum)
├── target_type: String | None ("booking", "review", "report", "follow")
├── target_id: UUID | None
├── is_read: Boolean (default False)
├── created_at: DateTime(timezone=True), server_default=now()
```

- `actor_id`: the user who triggered the event. Nullable for system/moderation notifications. `ON DELETE SET NULL` so notifications survive if the actor account is deleted.
- `target_type` + `target_id`: polymorphic reference (same pattern as Report model) for iOS client deep-linking.
- `type` enum values: `booking_joined`, `booking_accepted`, `booking_rejected`, `booking_cancelled`, `booking_confirmed`, `booking_completed`, `new_follower`, `new_mutual`, `review_revealed`, `report_resolved`, `account_warned`, `account_suspended`, `ideal_player_gained`, `ideal_player_lost`.
- No unique constraint — duplicate notifications are acceptable and cheap.

## Service Layer

**File:** `app/services/notification.py`

### create_notification(session, recipient_id, type, actor_id=None, target_type=None, target_id=None)

Creates and inserts a `Notification` row. Internal-only — never called directly from a router. No validation beyond what the DB enforces.

### list_notifications(session, user_id, limit=50, offset=0)

Returns notifications where `recipient_id = user_id`, ordered by `created_at desc`. Paginated with limit/offset.

### get_unread_count(session, user_id) → int

`SELECT COUNT(*) WHERE recipient_id = user_id AND is_read = False`.

### mark_as_read(session, user_id, notification_id)

1. Find notification by id
2. Verify `recipient_id == user_id` → `LookupError` (404) if not found or not owned
3. Set `is_read = True`, commit

### mark_all_as_read(session, user_id)

`UPDATE notifications SET is_read = True WHERE recipient_id = user_id AND is_read = False`. Commit.

## Integration Points

Notifications are created via direct `create_notification()` calls from existing services. No event bus.

| Service function | Trigger | Notification type | Recipient | Actor |
|-----------------|---------|-------------------|-----------|-------|
| `booking.join_booking` | After successful join | `booking_joined` | creator | joiner |
| `booking.respond_participant` (accept) | After accept | `booking_accepted` | participant | creator |
| `booking.respond_participant` (reject) | After reject | `booking_rejected` | participant | creator |
| `booking.cancel_booking` | After cancel | `booking_cancelled` | each participant | creator |
| `booking.confirm_booking` | After confirm | `booking_confirmed` | each participant | creator |
| `booking.complete_booking` | After complete | `booking_completed` | each participant | creator |
| `follow.create_follow` | After follow created | `new_follower` | followed user | follower |
| `follow.create_follow` | If mutual detected | `new_mutual` | original follower | followed user |
| `review.create_review` | If both reviews now exist (blind reveal) | `review_revealed` | both users | None |
| admin resolve report | After resolve | `report_resolved` | reporter | None |
| admin resolve report (warned) | After warn action | `account_warned` | target user | None |
| admin resolve report (suspended) | After suspend action | `account_suspended` | target user | None |
| `ideal_player.evaluate_ideal_status` | Status changed to True | `ideal_player_gained` | target user | None |
| `ideal_player.evaluate_ideal_status` | Status changed to False | `ideal_player_lost` | target user | None |

No block filtering on notifications — blocks already prevent the underlying actions.

## Schemas

**File:** `app/schemas/notification.py`

### NotificationResponse

```python
class NotificationResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    type: str
    target_type: str | None
    target_id: uuid.UUID | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
```

### UnreadCountResponse

```python
class UnreadCountResponse(BaseModel):
    unread_count: int
```

## Router

**File:** `app/routers/notifications.py`
**Registered at:** `/api/v1/notifications`

| Method | Path | Auth | Response | Description |
|--------|------|------|----------|-------------|
| GET | `/api/v1/notifications` | CurrentUser | list[NotificationResponse] | List my notifications (paginated) |
| GET | `/api/v1/notifications/unread-count` | CurrentUser | UnreadCountResponse | Get unread count |
| PATCH | `/api/v1/notifications/{notification_id}/read` | CurrentUser | 204 | Mark one as read |
| PATCH | `/api/v1/notifications/read-all` | CurrentUser | 204 | Mark all as read |

Query params on list endpoint: `limit` (default 50, max 100), `offset` (default 0).

Exception mapping:
- `LookupError` → 404

## i18n

No backend i18n keys needed. The notification `type` enum is sufficient for the iOS client to render localized strings. The backend stores and serves structured data only.

## Testing

**File:** `tests/test_notifications.py`

### Test cases

**List & count:**
- List notifications — returns correct list, ordered by newest first
- List with pagination — limit/offset works correctly
- Unread count — returns correct count
- Empty state — new user has 0 notifications, empty list

**Read management:**
- Mark one as read → 204, unread count decreases
- Mark already-read notification → 204 (idempotent)
- Mark notification owned by another user → 404
- Mark nonexistent notification → 404
- Mark all as read → 204, unread count becomes 0

**Notification creation (integration):**
- Join booking → creator gets `booking_joined` notification
- Accept participant → participant gets `booking_accepted`
- Reject participant → participant gets `booking_rejected`
- Cancel booking → all participants get `booking_cancelled`
- Confirm booking → all participants get `booking_confirmed`
- Complete booking → all participants get `booking_completed`
- Follow user → followed gets `new_follower`
- Mutual follow → original follower gets `new_mutual`
- Both reviews submitted → both users get `review_revealed`
- Admin resolves report → reporter gets `report_resolved`
- Admin warns user → target gets `account_warned`
- Admin suspends user → target gets `account_suspended`
- Ideal player status gained → user gets `ideal_player_gained`
- Ideal player status lost → user gets `ideal_player_lost`
