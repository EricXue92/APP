# Smart Matching (智能匹配) — Design Spec

## Overview

Smart matching helps users find compatible tennis partners and relevant open bookings automatically. It combines on-demand search with passive event-triggered notifications, using a weighted scoring algorithm to rank candidates.

Two matching modes:
- **User-to-user pairing** — system finds compatible players, one sends a proposal with concrete logistics, the other accepts/rejects. Acceptance auto-creates a booking. Singles only.
- **User-to-booking recommendation** — system recommends existing open bookings (singles and doubles) that fit the user's preferences.

---

## 1. Data Models

### 1.1 MatchPreference

One per user. Stores the user's matching profile.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users, unique |
| match_type | Enum(singles/doubles/any) | What the user is looking for |
| min_ntrp | String(10) | e.g. "3.0" |
| max_ntrp | String(10) | e.g. "4.0" |
| gender_preference | Enum(male_only/female_only/any) | |
| max_distance_km | Float | nullable, max distance from preferred courts |
| is_active | bool | default True, user toggle |
| last_active_at | DateTime | updated on authenticated requests, used for 30-day auto-expire |
| created_at | DateTime | |
| updated_at | DateTime | |

### 1.2 MatchTimeSlot

Weekly recurring availability. Multiple per preference.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| preference_id | UUID | FK → match_preferences |
| day_of_week | Integer | 0=Monday ... 6=Sunday |
| start_time | Time | half-hour granularity (00 or 30 minutes only) |
| end_time | Time | half-hour granularity (00 or 30 minutes only) |

Unique constraint: `(preference_id, day_of_week, start_time)`.

Half-hour granularity enforced at the Pydantic schema level:

```python
@field_validator("start_time", "end_time")
def must_be_half_hour(cls, v: time) -> time:
    if v.minute not in (0, 30):
        raise ValueError("Time must be on the hour or half hour")
    return v
```

### 1.3 MatchPreferenceCourt

Preferred courts. Multiple per preference.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| preference_id | UUID | FK → match_preferences |
| court_id | UUID | FK → courts |

Unique constraint: `(preference_id, court_id)`.

### 1.4 MatchProposal

Tracks the proposal lifecycle between two users.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| proposer_id | UUID | FK → users |
| target_id | UUID | FK → users |
| court_id | UUID | FK → courts |
| match_type | Enum(singles/doubles) | |
| play_date | Date | |
| start_time | Time | |
| end_time | Time | |
| message | Text | optional note from proposer |
| status | Enum(pending/accepted/rejected/expired) | |
| created_at | DateTime | |
| responded_at | DateTime | nullable |

No duplicate pending proposals to the same target: enforce in application logic (query for existing pending proposal between the same pair before insert).

---

## 2. Scoring Algorithm

Computes a score (0–100) for each candidate. Used for both user-to-user and user-to-booking matching.

### 2.1 Weights

| Factor | Weight | Logic |
|---|---|---|
| NTRP proximity | 35 | Full score if within ±0.5. Linear decay to 0 at ±1.5. Outside ±1.5 = filtered out. |
| Time overlap | 25 | Percentage of overlapping weekly time slots. No overlap = filtered out. |
| Court proximity | 20 | Shared preferred court → full score. Otherwise distance between nearest preferred courts, 0 km = full, linear decay to 0 at `max_distance_km`. If either user has no preferred courts, redistribute weight to other factors. |
| Credit score | 10 | `candidate.credit_score / 100 * 10` |
| Gender match | 5 | Binary: meets preference = full score, doesn't = filtered out. |
| Ideal player | 5 | `is_ideal_player` = 5, otherwise 0. |

### 2.2 Hard Filters (candidate excluded entirely)

- Blocked (either direction, via existing `is_blocked()`)
- Gender doesn't meet either user's preference
- NTRP gap > 1.5
- No time overlap
- User is suspended
- Matching is inactive or expired (last_active_at > 30 days)
- Same user

### 2.3 Soft Ranking

After hard filters, candidates are scored by the weighted formula, sorted descending. Top 10 returned.

### 2.4 User-to-Booking Scoring

Same weights, but comparing the user's preferences against each open booking's attributes:
- Booking's NTRP range vs user's NTRP level
- Booking's play_date + time mapped to day_of_week vs user's time slots
- Booking's court vs user's preferred courts
- Booking creator's credit score and ideal player status
- Booking's gender requirement vs user's gender

---

## 3. Proposal Lifecycle

### 3.1 State Machine

```
pending → accepted → (auto-creates booking)
pending → rejected
pending → expired   (48h with no response, checked lazily on read)
```

### 3.2 Flow

1. **User searches** — `GET /candidates` returns up to 10 ranked user matches; `GET /bookings` returns up to 10 ranked open bookings.
2. **User sends proposal** — `POST /proposals` with target_id, court_id, play_date, start/end time, optional message. Daily cap: 5 pending proposals per user.
3. **Target notified** — `MATCH_PROPOSAL_RECEIVED` notification.
4. **Target responds** — `PATCH /proposals/{id}` with `accepted` or `rejected`.
   - **Accepted:** auto-creates a Booking with proposer as creator, target as accepted participant. Both notified via `MATCH_PROPOSAL_ACCEPTED`.
   - **Rejected:** proposer notified via `MATCH_PROPOSAL_REJECTED`.
5. **Expiry** — proposals pending > 48h marked `expired` lazily on read. No background job needed.

### 3.3 Daily Cap Enforcement

Count proposals where `proposer_id = current_user` and `created_at >= today midnight UTC`. If >= 5, reject with 429.

---

## 4. Passive Matching (Event-Triggered)

### 4.1 Trigger Points

| Event | Action |
|---|---|
| User creates MatchPreference | Score against all active preferences, notify top 3 on both sides |
| User updates MatchPreference | Same |
| User reactivates is_active toggle | Same |

### 4.2 Behavior

- Uses the same scoring algorithm as on-demand search.
- Only notify if match score >= 60.
- New notification type: `MATCH_SUGGESTION`.
- Max 3 suggestions per trigger event.
- Don't re-suggest a pair that already has a pending/rejected proposal between them, or a suggestion notification sent within the last 7 days.

### 4.3 Auto-Expire Inactive Preferences

- `last_active_at` updated whenever the user hits any authenticated endpoint or completes a booking.
- Preferences with `last_active_at` > 30 days old: `is_active` set to `False` lazily — excluded from candidate search, and on the user's next login the preference response includes an `is_expired` flag so iOS can prompt reactivation.

---

## 5. API Endpoints

All under `/api/v1/matching/`.

### 5.1 Preferences

| Method | Path | Description |
|---|---|---|
| `POST` | `/preferences` | Create match preference with time slots + preferred courts. One per user (409 if exists). Triggers passive matching. |
| `GET` | `/preferences` | Get current user's preference (including time slots and courts). |
| `PUT` | `/preferences` | Full replace of preference, time slots, and courts. Triggers passive matching. |
| `PATCH` | `/preferences/toggle` | Toggle `is_active`. Reactivation triggers passive matching. |

### 5.2 Candidate Search

| Method | Path | Description |
|---|---|---|
| `GET` | `/candidates` | Up to 10 ranked user-to-user matches. Requires active preference. Singles pairing only. |
| `GET` | `/bookings` | Up to 10 ranked open bookings matching user's preference. Singles and doubles. |

### 5.3 Proposals

| Method | Path | Description |
|---|---|---|
| `POST` | `/proposals` | Send proposal with court, date, time, optional message. 429 if daily cap reached. |
| `GET` | `/proposals` | List sent + received proposals. Filterable by `direction=sent\|received` and `status`. |
| `PATCH` | `/proposals/{id}` | Accept or reject (target only). Accept auto-creates booking. |

---

## 6. Block, Suspension & Edge Cases

### 6.1 Block Integration

- Blocked pairs hard-filtered from candidate results (reuses `is_blocked()`).
- Cannot send a proposal to a blocked user (400).
- If a block happens while a proposal is pending, the proposal is auto-expired.

### 6.2 Suspension

- Suspended users excluded from candidate search.
- Suspended users cannot create preferences or send proposals (existing `get_current_user` dependency handles this).

### 6.3 Edge Cases

| Scenario | Behavior |
|---|---|
| Proposal accepted but court/time conflicts with another booking | Allowed — user is responsible for their schedule |
| Both users send proposals to each other | Both valid. If one accepted, the other stays pending. |
| User deactivates preference while having pending proposals | Preference deactivated, sent proposals remain active. User stops appearing in search. |
| Proposer's NTRP/gender changes after sending proposal | No retroactive validation — proposal was valid at send time. |
| Target accepts but proposer is now suspended | Reject acceptance with 400, auto-expire the proposal. |

---

## 7. New & Modified Files

### New Files

| File | Purpose |
|---|---|
| `app/models/matching.py` | MatchPreference, MatchTimeSlot, MatchPreferenceCourt, MatchProposal models |
| `app/schemas/matching.py` | Request/response Pydantic schemas with half-hour time validation |
| `app/services/matching.py` | Preference CRUD, scoring algorithm, candidate search, passive matching triggers |
| `app/services/match_proposal.py` | Proposal create/respond/expire, auto-create booking on accept |
| `app/routers/matching.py` | All `/api/v1/matching/` endpoints |
| Alembic migration | New tables: match_preferences, match_time_slots, match_preference_courts, match_proposals |

### Modified Files

| File | Change |
|---|---|
| `app/models/notification.py` | Add `MATCH_PROPOSAL_RECEIVED`, `MATCH_PROPOSAL_ACCEPTED`, `MATCH_PROPOSAL_REJECTED`, `MATCH_SUGGESTION` to NotificationType enum |
| `app/main.py` | Register matching router |

### Not Modified

- Existing booking flow unchanged — proposal acceptance calls the existing `create_booking()` service function.
- No changes to the booking, court, credit, review, or block services.
