# Phase 3b: Report/Block System Design

## Overview

Report and block system for Let's Tennis, enabling user moderation and safety. Users can report abusive content (reviews or users) and block other users. Admins resolve reports with escalating actions (dismiss → warn → hide content → suspend). Blocks are symmetric in effect and silent — blocked users see generic "not found" responses.

## Data Models

### Report

Table: `reports`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | default uuid4 |
| `reporter_id` | UUID FK → users | who filed the report |
| `reported_user_id` | UUID FK → users | who is being reported |
| `target_type` | Enum: `user`, `review` | what kind of content |
| `target_id` | UUID | review ID if target_type=review, reported_user_id if target_type=user |
| `reason` | Enum: `no_show`, `harassment`, `false_info`, `inappropriate`, `other` | report reason |
| `description` | Text, nullable | optional detail from reporter |
| `status` | Enum: `pending`, `resolved` | report lifecycle |
| `resolution` | Enum: `dismissed`, `warned`, `content_hidden`, `suspended`, nullable | set on resolve |
| `resolved_by` | UUID FK → users, nullable | admin who resolved |
| `resolved_at` | DateTime, nullable | when resolved |
| `created_at` | DateTime | server_default=now() |

When `target_type=user`, set `target_id = reported_user_id` to avoid NULL uniqueness issues in SQL.

Unique constraint: `(reporter_id, target_type, target_id)` — works for both review and user reports since `target_id` is always populated.

### Block

Table: `blocks`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | default uuid4 |
| `blocker_id` | UUID FK → users | who initiated the block |
| `blocked_id` | UUID FK → users | who is blocked |
| `created_at` | DateTime | server_default=now() |

Unique constraint: `(blocker_id, blocked_id)`.

### User Model Change

Add `is_suspended: bool` column (default `False`) to the `users` table. Checked at auth dependency level to deny access to all protected endpoints.

## Block Enforcement

When User A blocks User B, effects are **symmetric** (both sides affected) and **silent** (B is not notified):

| Feature | Enforcement | Implementation |
|---------|-------------|----------------|
| Join booking | B cannot join A's bookings, A cannot join B's | Check in `booking.join_booking()` — query Block table for pair in either direction |
| Reviews | Existing reviews between A↔B get `is_hidden=True`. New reviews between blocked pairs rejected | Block service hides on create. Review service checks blocks on submit |
| Booking listings | B's bookings hidden from A, A's bookings hidden from B | Filter in `booking.list_bookings()` — exclude where creator is in block pair |
| Future features | Chat, matching, follow will check Block table when built | Documented convention, no implementation now |

**Unblock behavior:** Block row is deleted (hard delete). Previously hidden reviews are NOT automatically restored — hiding was a moderation action. Booking/listing filters stop applying immediately.

## Suspension Enforcement

| Check Point | Behavior |
|-------------|----------|
| Login / Token refresh | Return 403 with i18n message "account suspended". Deny new tokens |
| Existing tokens | Add `is_suspended` check in `get_current_user` dependency — all protected endpoints reject suspended users immediately |

## API Endpoints

### Block Endpoints — `/api/v1/blocks`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/blocks` | Block a user. Body: `{"blocked_id": "uuid"}`. Returns 201. Silently hides mutual reviews |
| `DELETE` | `/api/v1/blocks/{blocked_id}` | Unblock a user. Only the blocker can unblock. Returns 204 |
| `GET` | `/api/v1/blocks` | List users I've blocked. Returns list of blocked user IDs + timestamps |

### Report Endpoints — `/api/v1/reports`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/reports` | Submit a report. Body: `{"reported_user_id", "target_type", "target_id?", "reason", "description?"}`. Returns 201 |
| `GET` | `/api/v1/reports/mine` | List my submitted reports + their status |

### Admin Endpoints — `/api/v1/admin/reports`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/reports` | List all reports. Filterable by `status` (pending/resolved). Paginated |
| `GET` | `/api/v1/admin/reports/{id}` | Get report detail including reporter info, target, and reported user history |
| `PATCH` | `/api/v1/admin/reports/{id}/resolve` | Resolve a report. Body: `{"resolution": "dismissed\|warned\|content_hidden\|suspended"}`. Executes side effects |

Admin endpoints require `UserRole.admin` or `UserRole.superadmin` role.

### Resolve Side Effects

| Resolution | Action |
|------------|--------|
| `dismissed` | No action, report marked resolved |
| `warned` | Report marked resolved with warning recorded (no system effect yet) |
| `content_hidden` | If target is a review, set `is_hidden=True`. Report marked resolved |
| `suspended` | Set `is_suspended=True` on reported user. Report marked resolved |

## Validation Rules

- Cannot block yourself — 400
- Cannot report yourself — 400
- Duplicate block — 409
- Duplicate report (same reporter + same target) — 409
- Report a review — review must exist and not already hidden
- Admin resolve — report must be in `pending` status
- `content_hidden` resolution — only valid when `target_type=review` (400 if target_type=user)
- Admin role check — `UserRole.admin` or `UserRole.superadmin` required

## File Structure

### New Files
- `app/models/report.py` — Report model
- `app/models/block.py` — Block model
- `app/schemas/report.py` — Pydantic schemas
- `app/schemas/block.py` — Pydantic schemas
- `app/services/report.py` — report business logic
- `app/services/block.py` — block business logic + enforcement
- `app/routers/blocks.py` — block endpoints
- `app/routers/reports.py` — report + admin endpoints
- `tests/test_blocks.py` — block tests
- `tests/test_reports.py` — report + admin tests
- `alembic/versions/xxx_.py` — migration (Report + Block + is_suspended)

### Modified Files
- `app/models/__init__.py` — export Report, Block
- `app/models/user.py` — add `is_suspended` field
- `app/dependencies.py` — add `is_suspended` check, add admin role dependency
- `app/services/booking.py` — block check in `join_booking()` + list filter
- `app/services/review.py` — block check in `submit_review()`
- `app/i18n.py` — new error/message keys
- `app/main.py` — register new routers

## Testing

All tests use real PostgreSQL (`lets_tennis_test`), no mocks. Follow existing `conftest.py` patterns.

### Block Tests
- Block user, unblock, list blocks
- Duplicate block (409), self-block (400), block nonexistent user
- Blocked user can't join booking
- Blocked user's bookings hidden from listing
- Review between blocked pair rejected
- Reviews hidden on block creation

### Report Tests
- Report user, report review
- Duplicate report (409), self-report (400), report hidden review (400)
- List my reports

### Admin Tests
- Dismiss report, warn, hide content (verify `is_hidden` set), suspend user (verify `is_suspended` set)
- Resolve already-resolved report (400)
- Non-admin access (403)

### Suspension Tests
- Suspended user can't login
- Suspended user's existing token rejected
