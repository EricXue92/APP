# Admin API Design Spec

## Overview

Consolidated admin API for Let's Tennis. Provides user management, court approval, report moderation, booking/event oversight, chat moderation, dashboard stats, and audit logging. All endpoints live under `/api/v1/admin/`.

## Decisions

- **Router structure:** Admin sub-package (`app/routers/admin/`) — one file per domain
- **Service layer:** Single `app/services/admin.py` — delegates to existing services where possible, adds admin-specific logic
- **Permission tiers:** Two-tier (admin + superadmin), no RBAC table
- **Dashboard:** Simple current counts, no time-series
- **Audit log:** `admin_audit_log` DB table, append-only

---

## 1. Data Model

### AdminAuditLog (`app/models/admin.py`)

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| admin_id | UUID FK → users | Who performed the action |
| action | AdminAction enum | Action type |
| target_type | String(50) | `user`, `court`, `report`, `booking`, `event`, `message` |
| target_id | UUID | ID of the affected resource |
| detail | Text (nullable) | JSON string with action-specific context (e.g., `{"old_role": "user", "new_role": "admin"}`) |
| created_at | DateTime | Timestamp |

### AdminAction Enum

```
user_suspended, user_unsuspended, user_role_changed, user_credit_reset,
court_approved, court_rejected, court_deleted,
report_resolved,
booking_cancelled,
event_cancelled, event_participant_removed,
message_deleted
```

No new fields on existing models — `is_suspended`, `is_approved`, `role`, etc. already exist.

---

## 2. Permission Tiers

### AdminUser (admin + superadmin) — day-to-day moderation

- List/search/view users
- Suspend users
- Reset credit score
- Approve/reject courts
- Resolve reports
- Cancel bookings
- Cancel events, remove participants
- Delete chat messages
- View dashboard stats
- View audit log

### SuperAdminUser (superadmin only) — destructive/sensitive operations

- Unsuspend users
- Change user roles
- Delete courts

### Implementation

New `require_superadmin` dependency in `app/dependencies.py`:

```python
async def require_superadmin(user: CurrentUser) -> User:
    if user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return user

SuperAdminUser = Annotated[User, Depends(require_superadmin)]
```

---

## 3. Router Structure & Endpoints

Sub-package `app/routers/admin/` with `__init__.py` exporting a single `admin_router`.

### `admin/users.py` — `/api/v1/admin/users`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Admin | List/search users (paginated, filter by role/city/suspended) |
| GET | `/{user_id}` | Admin | View user detail with stats |
| PATCH | `/{user_id}/suspend` | Admin | Suspend user |
| PATCH | `/{user_id}/unsuspend` | SuperAdmin | Unsuspend user |
| PATCH | `/{user_id}/role` | SuperAdmin | Change role (body: `{role: "admin"}`) |
| POST | `/{user_id}/reset-credit` | Admin | Reset credit score to 80, cancel_count to 0 |

### `admin/courts.py` — `/api/v1/admin/courts`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Admin | List courts (filter by is_approved, city) |
| PATCH | `/{court_id}/approve` | Admin | Set `is_approved = True` |
| PATCH | `/{court_id}/reject` | Admin | Delete an unapproved court (fails if already approved) |
| DELETE | `/{court_id}` | SuperAdmin | Delete an approved court |

### `admin/reports.py` — `/api/v1/admin/reports`

Migrated from existing `reports.admin_router`. Same endpoints:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Admin | List reports (filter by status, paginated) |
| GET | `/{report_id}` | Admin | View report detail |
| PATCH | `/{report_id}/resolve` | Admin | Resolve report (with side effects) |

### `admin/bookings.py` — `/api/v1/admin/bookings`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Admin | List bookings (paginated, filter by status) |
| PATCH | `/{booking_id}/cancel` | Admin | Force-cancel a booking |

### `admin/events.py` — `/api/v1/admin/events`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Admin | List events (paginated, filter by status) |
| PATCH | `/{event_id}/cancel` | Admin | Force-cancel an event |
| DELETE | `/{event_id}/participants/{user_id}` | Admin | Remove a participant |

### `admin/chat.py` — `/api/v1/admin/chat`

Migrated from existing `chat.admin_router`:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| DELETE | `/messages/{message_id}` | Admin | Delete a chat message |

### `admin/dashboard.py` — `/api/v1/admin/dashboard`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/stats` | Admin | Returns current counts |

Response:

```json
{
  "total_users": 142,
  "suspended_users": 3,
  "pending_reports": 5,
  "pending_courts": 2,
  "active_bookings": 18,
  "active_events": 4
}
```

### `admin/audit.py` — `/api/v1/admin/audit`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Admin | List audit log (paginated, filter by action/admin_id/target_type) |

### Registration in `main.py`

Remove existing per-module admin router includes. Replace with:

```python
from app.routers.admin import admin_router
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
```

---

## 4. Service Layer

Single `app/services/admin.py`, organized by domain.

### Audit logging

- `log_admin_action(session, admin_id, action, target_type, target_id, detail=None)` — creates `AdminAuditLog` entry. Called by every admin operation.
- `list_audit_logs(session, *, action, admin_id, target_type, limit, offset)` — filtered query for audit log endpoint.

### User management

- `list_users(session, *, role, city, is_suspended, limit, offset)` — filtered query on User table.
- `get_user_detail(session, user_id)` — returns user with stats (booking count, review avg, credit log count).
- `suspend_user(session, admin_id, user_id)` — sets `is_suspended=True`, logs audit, sends `ACCOUNT_SUSPENDED` notification.
- `unsuspend_user(session, admin_id, user_id)` — sets `is_suspended=False`, logs audit.
- `change_user_role(session, admin_id, user_id, new_role)` — validates not self-demotion, logs audit with old/new role in detail.
- `reset_user_credit(session, admin_id, user_id)` — sets `credit_score=80, cancel_count=0`, re-evaluates ideal player status, logs audit.

### Court management

- `list_all_courts(session, *, is_approved, city, limit, offset)` — delegates to existing `court.list_courts(approved_only=False)` with extra filters.
- `approve_court(session, admin_id, court_id)` — sets `is_approved=True`, logs audit.
- `reject_court(session, admin_id, court_id)` — validates court is unapproved, deletes it, logs audit.
- `delete_court(session, admin_id, court_id)` — deletes any court, logs audit.

### Booking management

- `list_all_bookings(session, *, status, limit, offset)` — query with filters.
- `admin_cancel_booking(session, admin_id, booking_id)` — delegates to existing `booking.cancel_booking()` logic for notifications/credit, logs audit.

### Event management

- `list_all_events(session, *, status, limit, offset)` — query with filters.
- `admin_cancel_event(session, admin_id, event_id)` — delegates to existing `event.cancel_event()`, logs audit.
- `admin_remove_participant(session, admin_id, event_id, user_id)` — removes participant, logs audit.

### Chat moderation

- `admin_delete_message(session, admin_id, message_id)` — deletes message, logs audit.

### Report management

- Existing `report.list_reports`, `report.resolve_report` are reused. Audit logging added as a wrapper around resolve.

### Dashboard

- `get_dashboard_stats(session)` — runs count queries, returns stats dict with: `total_users`, `suspended_users`, `pending_reports`, `pending_courts`, `active_bookings`, `active_events`.

---

## 5. Schemas

Single `app/schemas/admin.py`.

### Requests

- `UserRoleUpdateRequest` — `role: str` (validated against UserRole enum)
- No request body needed for suspend/unsuspend/approve/reject/cancel — action is implicit in the endpoint

### Responses

- `AdminUserResponse` — extends user profile with `is_suspended`, `credit_score`, `cancel_count`, `role`, `booking_count`, `avg_review`
- `AdminUserListResponse` — user list item (lighter than detail)
- `CourtAdminResponse` — includes `is_approved`, `created_by`
- `DashboardStatsResponse` — the 6 count fields
- `AuditLogEntry` — `id`, `admin_id`, `action`, `target_type`, `target_id`, `detail`, `created_at`

Reuse existing `ReportDetailResponse`, `EventResponse`, `BookingResponse` for list endpoints.

---

## 6. Testing

### Test file: `tests/test_admin.py`

Coverage areas:

- **Auth gates:** verify 403 for regular users on all admin endpoints; verify superadmin-only endpoints reject admin role
- **User management:** suspend/unsuspend, role change (including self-demotion guard), credit reset with ideal player re-eval
- **Court management:** approve/reject/delete flows, reject only works on unapproved courts
- **Booking/Event:** admin cancel triggers notifications, participant removal
- **Chat:** message deletion
- **Dashboard:** counts match actual data
- **Audit log:** entries created for every admin action, query filters work

### Fixtures

`conftest.py` additions: `admin_user`, `superadmin_user`, `admin_client`, `superadmin_client` helpers that create users with appropriate roles and return authenticated test clients.

---

## 7. Migration

Single Alembic migration:

- Create `admin_audit_log` table
- Create `adminaction` enum type in PostgreSQL

---

## 8. Changes to Existing Code

- `app/dependencies.py` — add `require_superadmin` + `SuperAdminUser`
- `app/main.py` — remove `reports.admin_router` and `chat.admin_router` includes, add single `admin_router` include
- `app/routers/reports.py` — remove `admin_router` and admin endpoints (migrated)
- `app/routers/chat.py` — remove `admin_router` and admin endpoint (migrated)
- Existing service functions (`cancel_booking`, `cancel_event`, `resolve_report`) are reused, not duplicated
