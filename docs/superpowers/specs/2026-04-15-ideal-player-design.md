# Ideal Player (理想球友) — Implementation Design

## Overview

Implement the ideal player evaluation service. The data model groundwork is already in place (`User.is_ideal_player` field, `NotificationType.IDEAL_PLAYER_GAINED/LOST` enums, booking list sort). This spec covers the evaluation logic, integration hooks, and tests.

## Core Evaluation Logic

**New file:** `app/services/ideal_player.py`

Single entry point:

```python
async def evaluate_ideal_status(session: AsyncSession, user_id: UUID) -> bool
```

### Conditions

All four must be met to mark a user as ideal player:

| Condition | Query |
|-----------|-------|
| Credit score >= 90 | `user.credit_score >= 90` (in-memory) |
| Never cancelled | `user.cancel_count == 0` (in-memory) |
| >= 10 completed bookings | `COUNT(BookingParticipant)` WHERE user_id=X, status=accepted, booking.status=completed |
| Average review rating >= 4.0 | `AVG((skill + punctuality + sportsmanship) / 3.0)` WHERE reviewee_id=X, is_hidden=False |

**Review scope decision:** Include all non-hidden reviews (option B). Hidden reviews (from admin report resolution) are excluded. Blind reveal status is irrelevant — ideal player is an objective backend assessment, not dependent on whether the other party submitted their review.

### Evaluation Flow

1. Load User from session
2. Short-circuit: check `credit_score` and `cancel_count` first (no DB query needed)
3. If those pass, query completed booking count
4. If that passes, query average review rating
5. Compare new status with `user.is_ideal_player`:
   - Changed to True: create `IDEAL_PLAYER_GAINED` notification
   - Changed to False: create `IDEAL_PLAYER_LOST` notification
   - No change: no notification
6. Update `user.is_ideal_player` and return new status

### Internal Helpers

- `_check_conditions(session, user) -> bool` — runs the four checks with short-circuit
- `_count_completed_bookings(session, user_id) -> int` — aggregate query
- `_avg_review_rating(session, user_id) -> float | None` — aggregate query, returns None if no reviews

## Integration Points

Two call sites, using direct invocation (consistent with existing notification pattern):

| Trigger | File | Evaluates | Reason |
|---------|------|-----------|--------|
| `apply_credit_change()` | `services/credit.py` | The user whose credit changed | Credit score or cancel_count changed |
| `submit_review()` | `services/review.py` | The reviewee | Average rating may have changed |

**Why not `complete_booking()`:** `complete_booking()` already calls `apply_credit_change()` for each accepted participant, which triggers evaluation. Adding a call in `complete_booking()` would cause redundant evaluation.

### Call Placement

- **`apply_credit_change()`**: Call `evaluate_ideal_status()` after updating credit_score/cancel_count and before `session.commit()`
- **`submit_review()`**: Call `evaluate_ideal_status(session, reviewee_id)` after creating the review and before `session.commit()`

## Tests

**New file:** `tests/test_ideal_player.py`

| Test | Description |
|------|-------------|
| Conditions not met — no mark | New user, defaults don't meet any condition, stays False |
| All conditions met — marked | Construct user meeting all 4 conditions, evaluates to True, GAINED notification created |
| Credit score insufficient | credit_score < 90, rest met, stays False |
| Has cancellations | cancel_count > 0, rest met, stays False |
| Insufficient bookings | < 10 completed bookings, rest met, stays False |
| Low review average | avg < 4.0, rest met, stays False |
| Demotion | Already ideal, cancel_count becomes 1, evaluates to False, LOST notification created |
| No change — no notification | Already ideal, still meets all conditions, no new notification |
| Integration: credit change triggers evaluation | Via `apply_credit_change()`, verify `is_ideal_player` updates |
| Integration: review triggers evaluation | Via `submit_review()`, verify `is_ideal_player` updates |

Tests construct ORM objects directly via session (consistent with existing test patterns, using real PostgreSQL test database).

## Files Changed

| File | Change |
|------|--------|
| `app/services/ideal_player.py` | **New** — evaluation logic |
| `app/services/credit.py` | Add `evaluate_ideal_status()` call at end of `apply_credit_change()` |
| `app/services/review.py` | Add `evaluate_ideal_status()` call in `submit_review()` for reviewee |
| `tests/test_ideal_player.py` | **New** — unit + integration tests |

## Not In Scope

- Booking assistant (约球助理) — separate feature, next phase
- Smart matching weight bonus — future enhancement
- Profile badge rendering — iOS frontend concern
