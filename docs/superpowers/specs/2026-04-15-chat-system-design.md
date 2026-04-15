# Chat System (聊天系统) Design Spec

## Overview

Real-time chat system for Let's Tennis, enabling participants of confirmed bookings to communicate. Chat rooms are auto-created when bookings are confirmed — private rooms for singles, group rooms for doubles. No user-initiated room creation.

**Architecture:** WebSocket for real-time delivery + REST endpoints for history/room listing. Single-process, in-memory connection manager. Messages persisted to PostgreSQL. No new external dependencies.

**Decisions:**
- Full WebSocket (not polling or SSE)
- Storage-agnostic media URLs (no specific storage backend for MVP)
- Simple keyword-based sensitive word filtering
- Rooms strictly auto-created by system triggers (no arbitrary DMs)
- Messages kept indefinitely (no TTL)
- `booking_card` message type for in-app booking forwarding (external sharing deferred to separate spec)

---

## 1. Data Models

### ChatRoom

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| type | enum: `private`, `group` | Private = singles booking, group = doubles booking |
| booking_id | UUID, FK → bookings.id, nullable, unique | The booking that triggered creation. Null for future event rooms. |
| name | String, nullable | Auto-generated for groups (e.g. "双打 @ 维园 4/20"), null for private |
| is_readonly | bool, default False | Set to True when booking is cancelled |
| created_at | datetime | server_default=func.now() |

### ChatParticipant

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| room_id | UUID, FK → chat_rooms.id | CASCADE on delete |
| user_id | UUID, FK → users.id | CASCADE on delete |
| joined_at | datetime | server_default=func.now() |
| last_read_at | datetime, nullable | Messages after this timestamp are "unread" |

Unique constraint on `(room_id, user_id)`.

### Message

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| room_id | UUID, FK → chat_rooms.id | CASCADE on delete |
| sender_id | UUID, FK → users.id | SET NULL on delete |
| type | enum: `text`, `image`, `location`, `booking_card` | |
| content | Text | Text content, image URL, JSON `{"lat":..,"lon":..,"label":..}`, or booking UUID |
| is_deleted | bool, default False | Soft delete for moderated messages |
| created_at | datetime | server_default=func.now() |

Index on `(room_id, created_at)` for paginated message queries.

**Message type details:**
- `text` — plain text in `content`
- `image` — URL string in `content` (storage-agnostic, actual upload is a separate concern)
- `location` — JSON string `{"lat": float, "lon": float, "label": str}` in `content`
- `booking_card` — booking UUID in `content`. Client fetches booking details via existing booking API to render a rich card.

---

## 2. Room Lifecycle

### Creation triggers

| Trigger | Room type | Participants |
|---------|-----------|-------------|
| Booking confirmed (singles) | `private` | The 2 accepted participants |
| Booking confirmed (doubles) | `group` | All accepted participants (2-4) |

Room creation happens inside `confirm_booking()` in `services/booking.py` — after status is set to `confirmed`, call `create_chat_room()` from `services/chat.py`.

### Participant changes

- Participant accepted after room exists (late join in doubles) → auto-added to room
- Participant cancelled/rejected → removed from room
- Booking cancelled → room becomes read-only (`is_readonly = True`). History preserved, no new messages.

### Block interaction

- User A blocks user B, they share a private room → room becomes read-only for both
- Group rooms: blocked users can both remain. Messages from blocked users are filtered client-side. Server still stores all messages.

---

## 3. WebSocket Connection & Messaging

### Connection flow

1. Client connects to `ws://host/api/v1/chat/ws?token=<JWT>`
2. Server validates JWT from query param
3. On connect: server loads all room IDs the user participates in, registers `user_id → WebSocket` in `ConnectionManager`
4. Heartbeat: client sends `ping` every 30s, server responds `pong`. No ping for 60s → server closes connection.

### ConnectionManager

Simple in-memory `dict[UUID, WebSocket]`. One connection per user — new connection replaces old. Sufficient for single-process MVP. Redis pub/sub can be added later for multi-worker scaling.

```python
class ConnectionManager:
    def __init__(self):
        self.connections: dict[uuid.UUID, WebSocket] = {}

    async def connect(self, user_id: uuid.UUID, ws: WebSocket) -> None
    async def disconnect(self, user_id: uuid.UUID) -> None
    async def broadcast_to_room(self, room_id: uuid.UUID, participant_ids: list[uuid.UUID], message: dict, exclude: uuid.UUID | None = None) -> None
```

### Sending a message

1. Client sends JSON over WebSocket:
   ```json
   {"action": "send", "room_id": "...", "type": "text", "content": "..."}
   ```
2. Server validates: user is participant, room is not read-only, content passes keyword filter (text only)
3. Message saved to PostgreSQL via `services/chat.py`
4. Server broadcasts to all other connected participants in the room
5. Server sends `ack` with message ID + timestamp to sender

### Server → client message format

```json
{
  "event": "new_message",
  "data": {
    "id": "uuid",
    "room_id": "uuid",
    "sender_id": "uuid",
    "sender_nickname": "string",
    "type": "text",
    "content": "hello",
    "created_at": "2026-04-15T10:30:00Z"
  }
}
```

### Error format

```json
{
  "event": "error",
  "data": {"code": "blocked_word", "message": "Message contains inappropriate content"}
}
```

---

## 4. REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/chat/rooms` | List my chat rooms (with last message + unread count) |
| GET | `/api/v1/chat/rooms/{room_id}/messages` | Paginated message history |
| POST | `/api/v1/chat/rooms/{room_id}/read` | Mark room as read (update `last_read_at`) |
| POST | `/api/v1/chat/rooms/{room_id}/messages` | Send message via REST (fallback for disconnected clients) |

### Room list response

Includes per room:
- Room ID, type, name, booking_id
- Other participants (id, nickname, avatar)
- Last message preview (type, content snippet, timestamp)
- Unread count (messages where `created_at > last_read_at`)

Block filtering: private rooms where the other user is blocked are excluded from the list.

### Message pagination

Cursor-based using `created_at` + `id` for stable ordering. Default page size 20. Client passes `?before=<message_id>` to load older messages.

---

## 5. Sensitive Word Filtering

- Keyword list file at `app/data/blocked_words.txt`, one word per line. Loaded into memory at startup.
- `filter_message(content: str) -> bool` — returns True if message contains a blocked word.
- Strategy: reject the message entirely and return an error. No partial masking.
- Only applied to `text` type messages. Image, location, and booking_card skip filtering.
- Checked in both WebSocket send handler and REST POST endpoint, before saving to DB.
- Update by editing the file and restarting. No admin API for MVP.

---

## 6. Reporting & Moderation

**Reuse existing report system.** `Report` model already supports polymorphic targets.

- Report a message: `target_type = "message"`, `target_id = message.id` via existing `POST /api/v1/reports`
- Admin resolves via existing `POST /api/v1/admin/reports/{id}/resolve`
- Soft delete: admin endpoint `DELETE /api/v1/admin/chat/messages/{id}` sets `message.is_deleted = True`
- Clients render deleted messages as "message removed"

### New notification type

`NEW_CHAT_MESSAGE` added to `NotificationType` — for unread badge on chat tab (in-app polling).

---

## 7. New Files & Integration Points

### New files

| File | Purpose |
|------|---------|
| `app/models/chat.py` | `ChatRoom`, `ChatParticipant`, `Message` models + enums (`RoomType`, `MessageType`) |
| `app/schemas/chat.py` | Request/response schemas |
| `app/services/chat.py` | Room CRUD, message sending, filtering, history, `ConnectionManager` |
| `app/routers/chat.py` | WebSocket endpoint + REST endpoints |
| `app/data/blocked_words.txt` | Sensitive word keyword list |
| Alembic migration | Tables: `chat_rooms`, `chat_participants`, `messages` |

### Modifications to existing files

| File | Change |
|------|--------|
| `app/models/__init__.py` | Import `ChatRoom`, `ChatParticipant`, `Message` |
| `app/main.py` | Register chat router + WebSocket route |
| `app/services/booking.py` | `confirm_booking()` → call `create_chat_room()` |
| `app/services/booking.py` | `cancel_booking()` → set chat room `is_readonly = True` |
| `app/services/booking.py` | `update_participant_status()` → add/remove chat participant on accept/cancel |
| `app/models/notification.py` | Add `NEW_CHAT_MESSAGE` to `NotificationType` |

### Untouched modules

Auth, credit, weather, matching, review, follow, assistant, court, ideal player — no changes.

---

## 8. Future Considerations (Not in Scope)

- **External sharing** — shareable booking links to Instagram/WeChat with deep linking (separate spec)
- **Event chat rooms** — auto-created for tournament participants (part of events spec)
- **Redis pub/sub** — for multi-worker WebSocket scaling (needed at 50万+ users)
- **Push notifications** — APNs integration for offline message delivery
- **Read receipts** — showing who has read messages in group chats
- **Message retention/cleanup** — TTL-based expiry if storage becomes a concern
