# Phase 3a: Review System (评价系统) — Design Spec

**Goal:** Allow participants to rate and review each other after a completed booking, building community trust through transparent feedback.

**Scope:** Review CRUD + blind reveal logic. Report/hide functionality deferred to Report/Block module (Phase 3c).

**Spec Reference:** `docs/superpowers/specs/2026-04-14-lets-tennis-design.md` section 5.2

---

## 1. Data Model

### 1.1 Review

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| booking_id | UUID (FK→bookings) | Required |
| reviewer_id | UUID (FK→users) | Required |
| reviewee_id | UUID (FK→users) | Required |
| skill_rating | Integer | 1-5, required |
| punctuality_rating | Integer | 1-5, required |
| sportsmanship_rating | Integer | 1-5, required |
| comment | Text | Nullable |
| is_hidden | Boolean | Default false. Reserved for Report/Block module |
| created_at | DateTime(tz) | server_default=now() |

Unique constraint on `(booking_id, reviewer_id, reviewee_id)` — one review per person per booking.

---

## 2. Blind Reveal Logic

Reviews use a double-blind system to encourage honest feedback:

- When user A reviews user B for a booking, the review is stored but **not visible** to B
- When user B also reviews user A for the same booking, **both reviews become visible** to each other
- A reviewer can always see their own submitted review (marked as "awaiting reciprocal review" until revealed)
- If only one side submits within the 24h window, that review is **never revealed** to the other party
- Public profile pages (`GET /reviews/users/{id}`) only show revealed reviews

**Implementation:** No status column needed. Visibility is determined at query time by checking if the reverse review exists (same `booking_id`, `reviewer_id`/`reviewee_id` swapped).

---

## 3. Time Window

- Reviews can only be submitted **after** the booking is completed
- The window is **24 hours** from the booking's completion time (`booking.updated_at` when status changed to `completed`)
- After 24h, unsubmitted reviews are forfeited (no record created, no penalty)

---

## 4. API Endpoints

### 4.1 Submit Review

| | |
|---|---|
| Method | POST |
| Path | `/api/v1/reviews` |
| Auth | Required |
| Body | `booking_id`, `reviewee_id`, `skill_rating`, `punctuality_rating`, `sportsmanship_rating`, `comment` (optional) |

**Validation rules:**
- Booking exists and `status = completed`
- Both reviewer and reviewee are `accepted` participants in the booking
- `reviewer_id ≠ reviewee_id`
- Within 24h window (based on `booking.updated_at`)
- Not a duplicate (unique constraint)
- All three ratings are integers in [1, 5]

### 4.2 Pending Reviews

| | |
|---|---|
| Method | GET |
| Path | `/api/v1/reviews/pending` |
| Auth | Required |

Returns bookings where the current user is an accepted participant, booking is completed, within 24h window, and the user has not yet reviewed all co-participants. Response includes booking info + list of reviewee candidates (user_id, nickname) not yet reviewed.

### 4.3 User Reviews

| | |
|---|---|
| Method | GET |
| Path | `/api/v1/reviews/users/{user_id}` |
| Auth | Not required |

Returns only revealed, non-hidden reviews for the target user. Includes:
- `average_skill`, `average_punctuality`, `average_sportsmanship` — dimension averages
- `total_reviews` — count of revealed reviews
- `reviews[]` — list with reviewer nickname, three ratings, comment, created_at

### 4.4 Booking Reviews

| | |
|---|---|
| Method | GET |
| Path | `/api/v1/reviews/bookings/{booking_id}` |
| Auth | Required |

Returns reviews for this booking that are relevant to the current user and revealed. A review is included if:
- Current user is the reviewer (always visible to self), OR
- Current user is the reviewee AND the reverse review exists (revealed)

---

## 5. Validation Rules Summary

| Rule | Error Key |
|------|-----------|
| Booking not completed | `review.booking_not_completed` |
| User not an accepted participant | `review.not_participant` |
| Reviewing self | `review.cannot_review_self` |
| Past 24h window | `review.window_expired` |
| Already reviewed this person for this booking | `review.already_submitted` |
| Rating not in [1, 5] | `review.invalid_rating` |

---

## 6. i18n Keys

| Key | zh-Hant | zh-Hans | en |
|-----|---------|---------|-----|
| `review.booking_not_completed` | 約球尚未完成 | 约球尚未完成 | Booking is not completed |
| `review.not_participant` | 你不是該約球的參與者 | 你不是该约球的参与者 | You are not a participant in this booking |
| `review.cannot_review_self` | 不能評價自己 | 不能评价自己 | Cannot review yourself |
| `review.window_expired` | 評價時間已過 | 评价时间已过 | Review window has expired |
| `review.already_submitted` | 你已經評價過此人 | 你已经评价过此人 | You have already reviewed this person |
| `review.invalid_rating` | 評分必須在 1-5 之間 | 评分必须在 1-5 之间 | Rating must be between 1 and 5 |

---

## 7. File Structure

```
app/
├── models/review.py          # Review model
├── schemas/review.py         # ReviewCreateRequest, ReviewResponse, UserReviewSummary, PendingReviewResponse
├── services/review.py        # Review logic + blind reveal checks
├── routers/reviews.py        # API endpoints
tests/
└── test_reviews.py           # Full lifecycle tests
alembic/
└── versions/xxxx_add_reviews.py
```

---

## 8. Testing Plan

- **Submit review:** success, booking not completed → rejected, non-participant → rejected, self-review → rejected, window expired → rejected, duplicate → rejected, invalid rating → rejected
- **Blind reveal:** single-side submit → not visible to other party; both sides submit → both visible; reviewer always sees own review
- **Pending reviews:** shows un-reviewed completed bookings in window; excludes expired windows; excludes already-reviewed participants
- **User reviews page:** only returns revealed + non-hidden reviews; averages calculated correctly; empty state when no revealed reviews
- **Booking reviews page:** returns self-submitted reviews; returns revealed reviews where user is reviewee; excludes unrevealed reviews from other pairs
