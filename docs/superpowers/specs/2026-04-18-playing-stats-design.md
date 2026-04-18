# Playing Statistics & Calendar View — Design Spec

## Overview

Add playing statistics and a calendar view to user profiles. Stats are public (visible to any authenticated user, subject to block checks). Data is computed at query time from existing `BookingParticipant` + `Booking` tables — no new tables or migrations.

## Endpoints

### `GET /api/v1/users/{user_id}/stats`

Returns aggregated playing statistics for a user.

**Auth:** Required. Block check — returns 404 if viewer and target have blocked each other.

**Response:**

```json
{
  "total_matches": 42,
  "monthly_matches": 6,
  "singles_count": 28,
  "doubles_count": 14,
  "top_courts": [
    {
      "court_id": "...",
      "court_name": "Victoria Park Tennis",
      "match_count": 15
    },
    { "court_id": "...", "court_name": "...", "match_count": 8 },
    { "court_id": "...", "court_name": "...", "match_count": 5 }
  ],
  "top_partners": [
    {
      "user_id": "...",
      "nickname": "Alice",
      "avatar_url": "...",
      "match_count": 7
    },
    {
      "user_id": "...",
      "nickname": "Bob",
      "avatar_url": "...",
      "match_count": 4
    },
    {
      "user_id": "...",
      "nickname": "Carol",
      "avatar_url": "...",
      "match_count": 3
    }
  ]
}
```

### `GET /api/v1/users/{user_id}/calendar?year=2026&month=4`

Returns dates with completed matches in the given month, with booking summaries.

**Auth:** Required. Same block check as stats.

**Query params:** `year` (int, required), `month` (int, required).

**Response:**

```json
{
  "year": 2026,
  "month": 4,
  "match_dates": [
    {
      "date": "2026-04-03",
      "bookings": [
        {
          "booking_id": "...",
          "court_name": "Victoria Park Tennis",
          "match_type": "singles",
          "start_time": "10:00",
          "end_time": "12:00",
          "participants": [{ "user_id": "...", "nickname": "Alice" }]
        }
      ]
    }
  ]
}
```

## Service Layer

**New file: `app/services/stats.py`**

### `get_user_stats(session, user_id) -> dict`

Five separate queries, all joining `BookingParticipant` (user_id, status=accepted) with `Booking` (status=completed):

1. **total_matches** — `COUNT` of completed bookings the user participated in
2. **monthly_matches** — same, filtered to current calendar month on `Booking.play_date`
3. **singles_count / doubles_count** — grouped by `Booking.match_type`
4. **top_courts (top 3)** — grouped by `Booking.court_id`, joined to `Court` for name, `ORDER BY count DESC LIMIT 3`
5. **top_partners (top 3)** — other `BookingParticipant` users in the same completed bookings (excluding self), grouped by `user_id`, joined to `User` for nickname/avatar, `ORDER BY count DESC LIMIT 3`

### `get_user_calendar(session, user_id, year, month) -> dict`

- Query `BookingParticipant` joined to `Booking` (status=completed, participant status=accepted, participant user_id matches)
- Filter `Booking.play_date` within the given year/month
- Join `Court` for court name, join other accepted participants for nickname (excluding the target user themselves)
- Group results by date in Python (max 31 days per result set)

## Schemas

**New file: `app/schemas/stats.py`**

```python
class CourtStats(BaseModel):
    court_id: UUID
    court_name: str
    match_count: int

class PartnerStats(BaseModel):
    user_id: UUID
    nickname: str
    avatar_url: str | None
    match_count: int

class UserStats(BaseModel):
    total_matches: int
    monthly_matches: int
    singles_count: int
    doubles_count: int
    top_courts: list[CourtStats]
    top_partners: list[PartnerStats]

class CalendarParticipant(BaseModel):
    user_id: UUID
    nickname: str

class CalendarBooking(BaseModel):
    booking_id: UUID
    court_name: str
    match_type: str
    start_time: str
    end_time: str
    participants: list[CalendarParticipant]

class CalendarDate(BaseModel):
    date: date
    bookings: list[CalendarBooking]

class UserCalendar(BaseModel):
    year: int
    month: int
    match_dates: list[CalendarDate]
```

All schemas use `model_config = {"from_attributes": True}`.

## Router Integration

Add two route functions to `app/routers/users.py`:

- `GET /api/v1/users/{user_id}/stats` → `get_user_stats()`
- `GET /api/v1/users/{user_id}/calendar` → `get_user_calendar()`

Both use `CurrentUser` for auth, `DbSession` for DB, and call `is_blocked()` before querying. If blocked, return 404.

## Testing

**New file: `tests/test_stats.py`**

| Test                                    | What it verifies                         |
| --------------------------------------- | ---------------------------------------- |
| Stats with no matches                   | Returns all zeros, empty lists           |
| Stats with completed matches            | Correct totals, singles/doubles split    |
| Top courts ranking                      | Correct order and limit of 3             |
| Top partners ranking                    | Correct order, limit of 3, excludes self |
| Monthly matches                         | Only counts current month                |
| Calendar correct dates                  | Completed bookings grouped by date       |
| Calendar excludes non-completed         | Open/cancelled bookings don't appear     |
| Calendar excludes rejected participants | Only accepted participants shown         |
| Block check                             | Blocked users get 404 on both endpoints  |
| Unauthenticated                         | Returns 401                              |

## What's NOT changing

- No new database tables or migrations
- No changes to existing booking/participant/court models
- No changes to existing service files
- No new dependencies

## Decisions

| Decision                  | Choice                    | Rationale                                                                       |
| ------------------------- | ------------------------- | ------------------------------------------------------------------------------- |
| Computation approach      | Query-time aggregation    | No sync bugs, always accurate, simple. Premature to optimize for scale.         |
| Stats visibility          | Public                    | Per design doc §5.3. Privacy controls can layer on top later (§1.3).            |
| Endpoint pattern          | Single `/{user_id}/stats` | Works for self and others. Block check handles access control.                  |
| Calendar granularity      | Month-based               | Matches iOS calendar pagination. Bounded query.                                 |
| Top courts/partners limit | 3                         | Matches design doc "Top 3" pattern.                                             |
| Date grouping             | Python-side               | Result set is small (max 31 days). Simpler than SQL grouping with nested joins. |
