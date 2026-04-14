# Phase 2: Booking System + Courts — Design Spec

**Goal:** Implement the core booking (约球) flow — users can browse courts, post match requests, join/confirm/cancel/complete bookings, with automatic credit score integration on cancellation and completion.

**Scope:** Post-a-match flow only (模式一：发布约球帖). Smart matching (模式二) deferred to a later phase.

**Spec Reference:** `docs/superpowers/specs/2026-04-14-lets-tennis-design.md` sections 2.1, 3, 12.3

---

## 1. Data Models

### 1.1 Court

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | String(100) | Required |
| address | String(255) | Required |
| city | String(50) | Required |
| latitude | Float | Nullable |
| longitude | Float | Nullable |
| court_type | Enum: indoor, outdoor | Required |
| surface_type | Enum: hard, clay, grass | Nullable |
| created_by | UUID (FK→users) | Nullable — null for admin-seeded |
| is_approved | Boolean | Default true for admin-seeded, false for user-submitted |
| created_at | DateTime(tz) | server_default=now() |

Only approved courts (`is_approved=true`) appear in listing endpoints.

### 1.2 Booking

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| creator_id | UUID (FK→users) | Required |
| court_id | UUID (FK→courts) | Required |
| match_type | Enum: singles, doubles | Required |
| play_date | Date | Required |
| start_time | Time | Required |
| end_time | Time | Required |
| min_ntrp | String(10) | e.g. "3.0" |
| max_ntrp | String(10) | e.g. "4.0" |
| gender_requirement | Enum: male_only, female_only, any | Default: any |
| max_participants | Integer | 2 for singles, 4 for doubles |
| cost_per_person | Integer | Nullable, in cents, display only |
| description | Text | Optional notes |
| status | Enum: open, confirmed, completed, cancelled | Default: open |
| created_at | DateTime(tz) | server_default=now() |
| updated_at | DateTime(tz) | server_default=now(), onupdate=now() |

Relationships: `creator` → User, `court` → Court, `participants` → BookingParticipant[]

### 1.3 BookingParticipant

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| booking_id | UUID (FK→bookings) | Required |
| user_id | UUID (FK→users) | Required |
| status | Enum: pending, accepted, rejected, cancelled | Default: pending |
| joined_at | DateTime(tz) | server_default=now() |
| updated_at | DateTime(tz) | server_default=now(), onupdate=now() |

Unique constraint on `(booking_id, user_id)` — a user can only join a booking once.

Creator is auto-added as first participant with `status=accepted`.

---

## 2. Booking Status State Machine

```
open → confirmed    (creator confirms, ≥2 accepted participants)
open → cancelled    (creator cancels)
confirmed → completed   (creator marks complete after play time)
confirmed → cancelled   (creator cancels before play time)
```

Individual participant statuses:
```
pending → accepted    (creator accepts)
pending → rejected    (creator rejects)
accepted → cancelled  (participant withdraws)
```

---

## 3. Cancellation Credit Penalty

Penalty tier is calculated automatically based on time remaining until play:

| Condition | Delta |
|-----------|-------|
| First-ever cancellation (cancel_count == 0) | 0 (warning only) |
| ≥ 24h before play | -1 |
| 12–24h before play | -2 |
| < 2h before play or no-show | -5 |
| Weather cancellation | 0 |

Play datetime = `booking.play_date` + `booking.start_time`.

Completion awards +5 credit to all accepted participants.

---

## 4. API Endpoints

### 4.1 Courts

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/v1/courts | No | List approved courts. Filters: city, court_type |
| GET | /api/v1/courts/{id} | No | Court detail |
| POST | /api/v1/courts | Yes | Submit a new court (is_approved=false) |

### 4.2 Bookings

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/v1/bookings | Yes | Create booking. Requires credit_score ≥ 60. Creator auto-joins as accepted. |
| GET | /api/v1/bookings | No | List open bookings. Filters: city, match_type, gender_requirement. NTRP filtering by requester level. |
| GET | /api/v1/bookings/my | Yes | My bookings (created or joined). Filter by status. |
| GET | /api/v1/bookings/{id} | No | Booking detail with participants |
| POST | /api/v1/bookings/{id}/join | Yes | Join a booking. Validates: NTRP in range, gender match, not already joined, booking not full, booking is open. |
| POST | /api/v1/bookings/{id}/confirm | Yes | Creator confirms. Requires ≥ 2 accepted participants. |
| POST | /api/v1/bookings/{id}/cancel | Yes | Cancel. Creator cancels = whole booking cancelled + credit penalties for creator. Participant cancels = only their participation cancelled + credit penalty for them. |
| POST | /api/v1/bookings/{id}/complete | Yes | Creator marks complete after play time. Awards +5 credit to all accepted participants. |
| PATCH | /api/v1/bookings/{id}/participants/{user_id} | Yes | Creator accepts/rejects a pending participant. |

### 4.3 Validation Rules

- **Create booking:** court must exist and be approved, creator credit_score ≥ 60, play_date must be in the future
- **Join:** booking must be `open`, user NTRP within `[min_ntrp, max_ntrp]`, gender matches requirement (or requirement is `any`), not already a participant, accepted count < max_participants
- **Confirm:** only creator, booking is `open`, ≥ 2 accepted participants
- **Cancel:** booking is `open` or `confirmed`, penalty calculated from play datetime
- **Complete:** only creator, booking is `confirmed`, current time ≥ play datetime

---

## 5. i18n Keys

New translation keys needed:

- `booking.not_found` — Booking not found
- `booking.not_open` — Booking is not open for joining
- `booking.already_joined` — You have already joined this booking
- `booking.full` — Booking is full
- `booking.ntrp_out_of_range` — Your NTRP level is outside the required range
- `booking.gender_mismatch` — This booking has a gender requirement you don't meet
- `booking.credit_too_low` — Credit score too low to create a booking
- `booking.not_creator` — Only the booking creator can perform this action
- `booking.not_enough_participants` — Not enough participants to confirm
- `booking.cannot_complete` — Booking cannot be completed yet
- `booking.already_cancelled` — Booking has already been cancelled
- `court.not_found` — Court not found
- `court.not_approved` — Court is not yet approved

---

## 6. File Structure

```
app/
├── models/
│   ├── court.py              # Court model + CourtType, SurfaceType enums
│   └── booking.py            # Booking, BookingParticipant models + enums
├── schemas/
│   ├── court.py              # CourtCreateRequest, CourtResponse, CourtListQuery
│   └── booking.py            # BookingCreateRequest, BookingResponse, etc.
├── services/
│   ├── court.py              # Court CRUD (list, get, create)
│   └── booking.py            # Booking logic (create, join, cancel, complete, confirm)
├── routers/
│   ├── courts.py             # Court endpoints
│   └── bookings.py           # Booking endpoints
tests/
├── test_courts.py            # Court CRUD + filtering tests
└── test_bookings.py          # Booking lifecycle + credit integration tests
alembic/
└── versions/
    └── xxxx_add_courts_bookings.py  # Migration for courts, bookings, booking_participants
```

---

## 7. Testing Plan

- **Court tests:** create court (user-submitted → unapproved), list only approved, filter by city/type, get by id
- **Booking create tests:** successful create, blocked when credit < 60, court must be approved, play_date in future
- **Booking join tests:** successful join, NTRP out of range rejected, gender mismatch rejected, duplicate join rejected, full booking rejected, only open bookings
- **Booking confirm tests:** only creator, needs ≥ 2 accepted participants
- **Booking cancel tests:** penalty tier calculation (mock datetime for 24h/12h/2h thresholds), first cancel = warning, creator cancel = whole booking cancelled
- **Booking complete tests:** only after play time, awards +5 credit to all accepted participants
- **Participant management tests:** creator accepts/rejects pending participants
