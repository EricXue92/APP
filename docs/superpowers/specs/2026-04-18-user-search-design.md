# User Search / Player Directory — Design Spec

## Overview

Add a player directory endpoint that lets authenticated users browse and filter other players. Supports keyword search, city/gender/NTRP filters, proximity-based court filtering, and ideal player filtering. Results sorted by activity recency with ideal players boosted.

## Endpoint

### `GET /api/v1/users/search`

**Auth:** Required (caller identity needed for block filtering and `is_following` field).

**Query Parameters:**

| Param        | Type              | Default | Description                                                        |
| ------------ | ----------------- | ------- | ------------------------------------------------------------------ |
| `keyword`    | string (optional) | —       | Partial match on nickname (case-insensitive ILIKE)                 |
| `city`       | string (optional) | —       | Exact match on city                                                |
| `gender`     | string (optional) | —       | `male` or `female`                                                 |
| `min_ntrp`   | string (optional) | —       | e.g. `"3.0"`                                                       |
| `max_ntrp`   | string (optional) | —       | e.g. `"4.5"`                                                       |
| `court_id`   | UUID (optional)   | —       | Reference court for proximity filter                               |
| `radius_km`  | float (optional)  | 10      | Search radius around reference court (max 50, requires `court_id`) |
| `ideal_only` | bool (optional)   | false   | Only show ideal players                                            |
| `page`       | int               | 1       | Page number                                                        |
| `page_size`  | int               | 20      | Results per page (max 50)                                          |

**Implicit filters (always applied):**

- Exclude the caller themselves
- Exclude blocked users (both directions via `is_blocked`)
- Exclude suspended users (`is_suspended = true`)
- Exclude inactive users (`is_active = false`)

**Response:**

```json
{
  "users": [
    {
      "id": "uuid",
      "nickname": "Player_A",
      "avatar_url": "https://...",
      "gender": "male",
      "city": "Hong Kong",
      "ntrp_level": "3.5",
      "ntrp_label": "中級 3.5",
      "bio": "Love doubles on weekends",
      "years_playing": 5,
      "is_ideal_player": true,
      "is_following": true,
      "last_active_at": "2026-04-15"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**Field notes:**

- `is_following`: whether the caller follows this user. Derived from the Follow table at query time so the frontend can render follow/unfollow without a second API call.
- `last_active_at`: most recent completed booking `play_date`. `null` if the user has never completed a booking (sorts last).
- `credit_score` is deliberately excluded — internal metric, not for public directory display.

## Sorting

Default sort order:

1. `is_ideal_player DESC` — ideal players surface first
2. `last_active_at DESC NULLS LAST` — most recently active within each tier

`last_active_at` is computed as a subquery: `MAX(booking.play_date)` from completed bookings where the user was an accepted participant. Not stored on the User model.

## Court Proximity Filter

When `court_id` is provided:

1. Look up the reference court's `latitude`/`longitude`
2. Find all courts within `radius_km` using the haversine formula (existing pattern from the matching module)
3. Find users who are associated with any of those nearby courts via EITHER:
   - Completed bookings at those courts (via `BookingParticipant` + `Booking.court_id`)
   - Match preferences listing those courts (via `MatchPreferenceCourt`)
4. Filter the user list to only include those users

When `court_id` is omitted, no geographic filter is applied. The `city` filter is a separate, coarser option — the two can be used independently or together.

`radius_km` is ignored if `court_id` is not provided.

## NTRP Range Filter

Uses the existing `_ntrp_to_float()` helper to convert NTRP strings to floats for comparison. When provided, filters: `min_ntrp <= user.ntrp_level <= max_ntrp`.

## Service Layer

**New file: `app/services/user_search.py`**

- `search_users(session, *, caller_id, keyword, city, gender, min_ntrp, max_ntrp, court_id, radius_km, ideal_only, page, page_size) -> dict`
  - Builds a dynamic query with all filters
  - Returns `{"users": [...], "total": int}`
  - Each user dict includes `is_following` and `last_active_at`

Uses haversine helper from matching module for court distance calculations.

## Schemas

**New file: `app/schemas/user_search.py`**

```python
class UserSearchItem(BaseModel):
    id: uuid.UUID
    nickname: str
    avatar_url: str | None
    gender: str
    city: str
    ntrp_level: str
    ntrp_label: str
    bio: str | None
    years_playing: int | None
    is_ideal_player: bool
    is_following: bool
    last_active_at: date | None

class UserSearchResponse(BaseModel):
    users: list[UserSearchItem]
    total: int
    page: int
    page_size: int
```

All with `model_config = {"from_attributes": True}`.

## Router

**Modify: `app/routers/users.py`**

Add `GET /search` endpoint. Must be defined BEFORE `GET /{user_id}/stats` to avoid path conflicts (FastAPI matches routes in order).

Uses `CurrentUser`, `DbSession`, `Lang` dependencies.

## Testing

**New file: `tests/test_user_search.py`**

| Test                              | What it verifies                                    |
| --------------------------------- | --------------------------------------------------- |
| Search returns users              | Basic happy path with seeded users                  |
| Caller excluded from results      | Searcher doesn't see themselves                     |
| Blocked users excluded            | Both directions of block filtering                  |
| Suspended/inactive excluded       | Only active, non-suspended users returned           |
| Keyword filter                    | Partial nickname match, case-insensitive            |
| City filter                       | Exact city match                                    |
| Gender filter                     | Only matching gender returned                       |
| NTRP range filter                 | Users outside range excluded                        |
| Court proximity filter            | Users who play at nearby courts returned            |
| Court proximity respects radius   | Users at far courts excluded                        |
| Court filter includes preferences | Users with matching `MatchPreferenceCourt` included |
| Ideal only filter                 | Only ideal players when `ideal_only=true`           |
| Sort order                        | Ideal players first, then by last_active_at         |
| Pagination                        | Correct page/page_size/total behavior               |
| is_following field                | True when caller follows the user, false otherwise  |
| No filters returns all eligible   | Empty params returns full directory                 |

## What's NOT Changing

- No new database tables or migrations
- No changes to existing User model
- No changes to existing matching/follow/block modules
- No new dependencies

## Decisions

| Decision              | Choice                                    | Rationale                                                 |
| --------------------- | ----------------------------------------- | --------------------------------------------------------- |
| Auth required         | Yes                                       | Need caller identity for block filtering and is_following |
| Court filter          | Proximity-based (haversine)               | City-level is too coarse; single court is too narrow      |
| Court association     | Booking history + match preferences       | Broadest coverage of user-court relationships             |
| last_active_at        | Computed at query time                    | Avoids new columns/migrations; dataset size is manageable |
| Sort order            | Ideal players first, then recently active | Rewards good behavior and active community members        |
| credit_score visible  | No                                        | Internal metric, not for public display                   |
| is_following included | Yes                                       | Saves frontend a round-trip per user                      |
