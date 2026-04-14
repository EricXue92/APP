# Ideal Player (理想球友) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the ideal player evaluation service that automatically marks/unmarks users based on credit score, cancel history, booking count, and review ratings.

**Architecture:** Single service module (`ideal_player.py`) with one public function `evaluate_ideal_status()`. Integrated into two existing services (`credit.py`, `review.py`) via direct call. Data model and notification enums already exist.

**Tech Stack:** SQLAlchemy async, PostgreSQL, pytest-asyncio

---

### Task 1: Core evaluation service — failing tests

**Files:**
- Create: `tests/test_ideal_player.py`

- [ ] **Step 1: Write test helper and first unit tests**

```python
import uuid
from datetime import date, time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, MatchType, GenderRequirement, ParticipantStatus
from app.models.court import Court, CourtType
from app.models.notification import Notification, NotificationType
from app.models.review import Review
from app.models.user import AuthProvider
from app.services.ideal_player import evaluate_ideal_status
from app.services.user import create_user_with_auth


async def _create_user(session: AsyncSession, username: str, credit_score: int = 95) -> "User":
    user = await create_user_with_auth(
        session,
        nickname=f"Player_{username}",
        gender="male",
        city="Hong Kong",
        ntrp_level="3.5",
        language="en",
        provider=AuthProvider.USERNAME,
        provider_user_id=username,
        password="test1234",
    )
    user.credit_score = credit_score
    await session.commit()
    await session.refresh(user)
    return user


async def _create_court(session: AsyncSession) -> Court:
    court = Court(
        name="Test Court",
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.flush()
    return court


async def _seed_completed_bookings(session: AsyncSession, user_id: uuid.UUID, count: int) -> None:
    """Create `count` completed bookings with user as accepted participant."""
    court = await _create_court(session)
    for i in range(count):
        booking = Booking(
            creator_id=user_id,
            court_id=court.id,
            match_type=MatchType.SINGLES,
            play_date=date(2026, 1, 1 + i),
            start_time=time(10, 0),
            end_time=time(12, 0),
            min_ntrp="3.0",
            max_ntrp="4.0",
            gender_requirement=GenderRequirement.ANY,
            max_participants=2,
            status=BookingStatus.COMPLETED,
        )
        session.add(booking)
        await session.flush()
        participant = BookingParticipant(
            booking_id=booking.id,
            user_id=user_id,
            status=ParticipantStatus.ACCEPTED,
        )
        session.add(participant)
    await session.flush()


async def _seed_reviews(session: AsyncSession, reviewee_id: uuid.UUID, ratings: list[tuple[int, int, int]]) -> None:
    """Create reviews for user with given (skill, punctuality, sportsmanship) ratings."""
    for i, (skill, punct, sport) in enumerate(ratings):
        reviewer = await _create_user(session, f"reviewer_{reviewee_id.hex[:6]}_{i}")
        court = await _create_court(session)
        booking = Booking(
            creator_id=reviewer.id,
            court_id=court.id,
            match_type=MatchType.SINGLES,
            play_date=date(2026, 3, 1 + i),
            start_time=time(10, 0),
            end_time=time(12, 0),
            min_ntrp="3.0",
            max_ntrp="4.0",
            gender_requirement=GenderRequirement.ANY,
            max_participants=2,
            status=BookingStatus.COMPLETED,
        )
        session.add(booking)
        await session.flush()
        review = Review(
            booking_id=booking.id,
            reviewer_id=reviewer.id,
            reviewee_id=reviewee_id,
            skill_rating=skill,
            punctuality_rating=punct,
            sportsmanship_rating=sport,
        )
        session.add(review)
    await session.flush()


@pytest.mark.asyncio
async def test_not_ideal_by_default(session: AsyncSession):
    """New user with default values should not be ideal."""
    user = await _create_user(session, "default_user", credit_score=80)
    result = await evaluate_ideal_status(session, user.id)
    assert result is False
    assert user.is_ideal_player is False


@pytest.mark.asyncio
async def test_all_conditions_met(session: AsyncSession):
    """User meeting all 4 conditions becomes ideal player with GAINED notification."""
    user = await _create_user(session, "ideal_user", credit_score=95)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is True
    assert user.is_ideal_player is True

    # Check GAINED notification
    from sqlalchemy import select
    notifs = (await session.execute(
        select(Notification).where(
            Notification.recipient_id == user.id,
            Notification.type == NotificationType.IDEAL_PLAYER_GAINED,
        )
    )).scalars().all()
    assert len(notifs) == 1


@pytest.mark.asyncio
async def test_credit_score_insufficient(session: AsyncSession):
    user = await _create_user(session, "low_credit", credit_score=85)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_has_cancellations(session: AsyncSession):
    user = await _create_user(session, "cancelled_user", credit_score=95)
    user.cancel_count = 1
    await session.flush()
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_insufficient_bookings(session: AsyncSession):
    user = await _create_user(session, "few_bookings", credit_score=95)
    await _seed_completed_bookings(session, user.id, 9)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_low_review_average(session: AsyncSession):
    user = await _create_user(session, "low_reviews", credit_score=95)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(3, 3, 3)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_demotion(session: AsyncSession):
    """Already ideal player loses status when condition fails."""
    user = await _create_user(session, "demoted_user", credit_score=95)
    user.is_ideal_player = True
    await session.flush()
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    # Break a condition
    user.cancel_count = 1
    await session.flush()

    result = await evaluate_ideal_status(session, user.id)
    assert result is False
    assert user.is_ideal_player is False

    # Check LOST notification
    from sqlalchemy import select
    notifs = (await session.execute(
        select(Notification).where(
            Notification.recipient_id == user.id,
            Notification.type == NotificationType.IDEAL_PLAYER_LOST,
        )
    )).scalars().all()
    assert len(notifs) == 1


@pytest.mark.asyncio
async def test_no_change_no_notification(session: AsyncSession):
    """Re-evaluating an already-ideal user with no changes produces no new notification."""
    user = await _create_user(session, "stable_user", credit_score=95)
    user.is_ideal_player = True
    await session.flush()
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is True

    from sqlalchemy import select
    notifs = (await session.execute(
        select(Notification).where(Notification.recipient_id == user.id)
    )).scalars().all()
    assert len(notifs) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ideal_player.py -v`
Expected: ImportError — `cannot import name 'evaluate_ideal_status' from 'app.services.ideal_player'`

- [ ] **Step 3: Commit**

```bash
git add tests/test_ideal_player.py
git commit -m "test: add ideal player evaluation tests (red)"
```

---

### Task 2: Core evaluation service — implementation

**Files:**
- Create: `app/services/ideal_player.py`

- [ ] **Step 1: Implement the evaluation service**

```python
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.notification import NotificationType
from app.models.review import Review
from app.models.user import User
from app.services.notification import create_notification

CREDIT_THRESHOLD = 90
MIN_COMPLETED_BOOKINGS = 10
MIN_AVG_RATING = 4.0


async def evaluate_ideal_status(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Evaluate and update ideal player status. Returns the new status."""
    user = await session.get(User, user_id)
    if user is None:
        return False

    was_ideal = user.is_ideal_player
    is_ideal = await _check_conditions(session, user)
    user.is_ideal_player = is_ideal

    if is_ideal != was_ideal:
        await create_notification(
            session,
            recipient_id=user_id,
            type=(
                NotificationType.IDEAL_PLAYER_GAINED
                if is_ideal
                else NotificationType.IDEAL_PLAYER_LOST
            ),
        )

    return is_ideal


async def _check_conditions(session: AsyncSession, user: User) -> bool:
    if user.credit_score < CREDIT_THRESHOLD:
        return False
    if user.cancel_count != 0:
        return False

    completed = await _count_completed_bookings(session, user.id)
    if completed < MIN_COMPLETED_BOOKINGS:
        return False

    avg = await _avg_review_rating(session, user.id)
    if avg is None or avg < MIN_AVG_RATING:
        return False

    return True


async def _count_completed_bookings(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(BookingParticipant.id))
        .join(Booking, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
    )
    return result.scalar_one()


async def _avg_review_rating(session: AsyncSession, user_id: uuid.UUID) -> float | None:
    """Average of all three rating dimensions across all non-hidden reviews received."""
    result = await session.execute(
        select(
            func.avg(
                (Review.skill_rating + Review.punctuality_rating + Review.sportsmanship_rating)
                / 3.0
            )
        ).where(
            Review.reviewee_id == user_id,
            Review.is_hidden == False,  # noqa: E712
        )
    )
    val = result.scalar_one()
    return float(val) if val is not None else None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_ideal_player.py -v`
Expected: All 8 tests PASS

- [ ] **Step 3: Commit**

```bash
git add app/services/ideal_player.py
git commit -m "feat: add ideal player evaluation service"
```

---

### Task 3: Integrate into credit service

**Files:**
- Modify: `app/services/credit.py:27-49` (the `apply_credit_change` function)

- [ ] **Step 1: Write integration test**

Add to `tests/test_ideal_player.py`:

```python
from app.models.credit import CreditReason
from app.services.credit import apply_credit_change


@pytest.mark.asyncio
async def test_credit_change_triggers_evaluation(session: AsyncSession):
    """apply_credit_change should trigger ideal player evaluation."""
    user = await _create_user(session, "credit_trigger", credit_score=90)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    # Attend a booking — credit goes to 95, all conditions met
    await apply_credit_change(session, user, CreditReason.ATTENDED)

    await session.refresh(user)
    assert user.is_ideal_player is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ideal_player.py::test_credit_change_triggers_evaluation -v`
Expected: FAIL — `assert user.is_ideal_player is True` (still False because hook not added)

- [ ] **Step 3: Add hook in credit.py**

In `app/services/credit.py`, add the import at the top:

```python
from app.services.ideal_player import evaluate_ideal_status
```

Then in `apply_credit_change()`, add the call before `session.commit()` (after line 46, before line 47):

```python
    session.add(log)
    await evaluate_ideal_status(session, user.id)
    await session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ideal_player.py tests/test_credit.py -v`
Expected: All tests PASS (both new integration test and existing credit tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/credit.py tests/test_ideal_player.py
git commit -m "feat: trigger ideal player evaluation on credit change"
```

---

### Task 4: Integrate into review service

**Files:**
- Modify: `app/services/review.py:128` (in `submit_review`, before `session.commit()`)

- [ ] **Step 1: Write integration test**

Add to `tests/test_ideal_player.py`:

```python
from datetime import datetime, timezone

from app.services.review import submit_review


@pytest.mark.asyncio
async def test_review_triggers_evaluation(session: AsyncSession):
    """submit_review should trigger ideal player evaluation for the reviewee."""
    reviewee = await _create_user(session, "review_target", credit_score=95)
    reviewer = await _create_user(session, "review_author", credit_score=80)
    await _seed_completed_bookings(session, reviewee.id, 10)
    # Seed reviews that bring average to >= 4.0
    await _seed_reviews(session, reviewee.id, [(5, 5, 5)] * 2)

    # Create a completed booking between reviewer and reviewee
    court = await _create_court(session)
    booking = Booking(
        creator_id=reviewer.id,
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=date(2026, 4, 1),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        gender_requirement=GenderRequirement.ANY,
        max_participants=2,
        status=BookingStatus.COMPLETED,
    )
    session.add(booking)
    await session.flush()
    for uid in [reviewer.id, reviewee.id]:
        session.add(BookingParticipant(
            booking_id=booking.id,
            user_id=uid,
            status=ParticipantStatus.ACCEPTED,
        ))
    await session.commit()

    # Submit review — this should trigger evaluation
    await submit_review(
        session,
        booking_id=booking.id,
        reviewer=reviewer,
        reviewee_id=reviewee.id,
        skill_rating=5,
        punctuality_rating=5,
        sportsmanship_rating=5,
    )

    await session.refresh(reviewee)
    assert reviewee.is_ideal_player is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ideal_player.py::test_review_triggers_evaluation -v`
Expected: FAIL — `assert reviewee.is_ideal_player is True` (still False)

- [ ] **Step 3: Add hook in review.py**

In `app/services/review.py`, add the import at the top:

```python
from app.services.ideal_player import evaluate_ideal_status
```

Then in `submit_review()`, add the call before `await session.commit()` (before line 128):

```python
    # Evaluate ideal player status for reviewee
    await evaluate_ideal_status(session, reviewee_id)

    await session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ideal_player.py tests/test_reviews.py -v`
Expected: All tests PASS (both new integration test and existing review tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/review.py tests/test_ideal_player.py
git commit -m "feat: trigger ideal player evaluation on review submit"
```

---

### Task 5: Run full test suite

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests pass. No regressions from ideal player integration.

- [ ] **Step 2: Commit (if any fixes needed)**

Only if fixes were applied. Otherwise skip.
