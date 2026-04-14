# Review System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow booking participants to rate and review each other after a completed booking, with double-blind reveal logic.

**Architecture:** New Review model + service + router following existing patterns (service handles business logic, router handles HTTP + validation). Blind reveal is computed at query time by checking for reverse reviews — no status column needed.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, pytest + httpx

---

### Task 1: Review Model + Migration

**Files:**
- Create: `app/models/review.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Create Review model**

Create `app/models/review.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("booking_id", "reviewer_id", "reviewee_id", name="uq_reviews_booking_reviewer_reviewee"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    reviewee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    skill_rating: Mapped[int] = mapped_column(Integer)
    punctuality_rating: Mapped[int] = mapped_column(Integer)
    sportsmanship_rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    is_hidden: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    booking: Mapped["Booking"] = relationship(foreign_keys=[booking_id])
    reviewer: Mapped["User"] = relationship(foreign_keys=[reviewer_id])
    reviewee: Mapped["User"] = relationship(foreign_keys=[reviewee_id])
```

- [ ] **Step 2: Export Review in models __init__**

Add to `app/models/__init__.py`:

```python
from app.models.review import Review
```

And add `"Review"` to the `__all__` list.

- [ ] **Step 3: Generate and apply migration**

Run:
```bash
uv run alembic revision --autogenerate -m "add reviews table"
uv run alembic upgrade head
```

Expected: Migration file created, `reviews` table added to database.

- [ ] **Step 4: Commit**

```bash
git add app/models/review.py app/models/__init__.py alembic/versions/
git commit -m "feat: add Review model and migration"
```

---

### Task 2: Review Schemas

**Files:**
- Create: `app/schemas/review.py`

- [ ] **Step 1: Create review schemas**

Create `app/schemas/review.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreateRequest(BaseModel):
    booking_id: uuid.UUID
    reviewee_id: uuid.UUID
    skill_rating: int = Field(..., ge=1, le=5)
    punctuality_rating: int = Field(..., ge=1, le=5)
    sportsmanship_rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class ReviewResponse(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewee_id: uuid.UUID
    reviewer_nickname: str
    skill_rating: int
    punctuality_rating: int
    sportsmanship_rating: int
    comment: str | None
    is_revealed: bool
    created_at: datetime


class UserReviewSummary(BaseModel):
    average_skill: float
    average_punctuality: float
    average_sportsmanship: float
    total_reviews: int
    reviews: list[ReviewResponse]


class PendingReviewItem(BaseModel):
    booking_id: uuid.UUID
    court_name: str
    play_date: str
    reviewees: list[dict]  # [{"user_id": ..., "nickname": ...}]
    window_closes_at: datetime
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/review.py
git commit -m "feat: add review Pydantic schemas"
```

---

### Task 3: i18n Keys

**Files:**
- Modify: `app/i18n.py`

- [ ] **Step 1: Add review i18n keys**

Add the following entries to the `_MESSAGES` dict in `app/i18n.py`, after the `"court.not_approved"` entry:

```python
    "review.booking_not_completed": {
        "zh-Hans": "约球尚未完成",
        "zh-Hant": "約球尚未完成",
        "en": "Booking is not completed",
    },
    "review.not_participant": {
        "zh-Hans": "你不是该约球的参与者",
        "zh-Hant": "你不是該約球的參與者",
        "en": "You are not a participant in this booking",
    },
    "review.cannot_review_self": {
        "zh-Hans": "不能评价自己",
        "zh-Hant": "不能評價自己",
        "en": "Cannot review yourself",
    },
    "review.window_expired": {
        "zh-Hans": "评价时间已过",
        "zh-Hant": "評價時間已過",
        "en": "Review window has expired",
    },
    "review.already_submitted": {
        "zh-Hans": "你已经评价过此人",
        "zh-Hant": "你已經評價過此人",
        "en": "You have already reviewed this person",
    },
    "review.invalid_rating": {
        "zh-Hans": "评分必须在 1-5 之间",
        "zh-Hant": "評分必須在 1-5 之間",
        "en": "Rating must be between 1 and 5",
    },
```

- [ ] **Step 2: Commit**

```bash
git add app/i18n.py
git commit -m "feat: add review i18n keys"
```

---

### Task 4: Review Service — Submit + Blind Reveal

**Files:**
- Create: `app/services/review.py`
- Test: `tests/test_reviews.py`

- [ ] **Step 1: Write failing tests for submit_review**

Create `tests/test_reviews.py`:

```python
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.user import User


async def _register_and_get_token(client: AsyncClient, username: str, gender: str = "male", ntrp: str = "3.5") -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": gender,
            "city": "Hong Kong",
            "ntrp_level": ntrp,
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


async def _seed_court(session: AsyncSession) -> Court:
    court = Court(
        name="Test Court",
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


def _future_date() -> str:
    return (date.today() + timedelta(days=7)).isoformat()


async def _create_completed_booking(client: AsyncClient, session: AsyncSession, token1: str, token2: str, court_id: str) -> str:
    """Create a booking, join, accept, confirm, backdate, and complete. Returns booking_id."""
    # Create
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": court_id,
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
        },
    )
    booking_id = resp.json()["id"]

    # Join and accept
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    detail = await client.get(f"/api/v1/bookings/{booking_id}")
    joiner_id = detail.json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Confirm
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})

    # Backdate play_date to past so complete works
    from app.models.booking import Booking
    from sqlalchemy import update
    await session.execute(
        update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    # Complete
    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers={"Authorization": f"Bearer {token1}"})

    return booking_id


# --- Submit Review Tests ---


@pytest.mark.asyncio
async def test_submit_review_success(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_host1")
    token2, user_id2 = await _register_and_get_token(client, "rev_join1")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 4,
            "comment": "Great player!",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reviewer_id"] == user_id1
    assert data["reviewee_id"] == user_id2
    assert data["skill_rating"] == 4
    assert data["is_revealed"] is False  # other side hasn't reviewed yet


@pytest.mark.asyncio
async def test_submit_review_booking_not_completed(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_host2")
    token2, user_id2 = await _register_and_get_token(client, "rev_join2")
    court = await _seed_court(session)

    # Create booking but don't complete it
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    booking_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_submit_review_not_participant(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_host3")
    token2, user_id2 = await _register_and_get_token(client, "rev_join3")
    token3, user_id3 = await _register_and_get_token(client, "rev_outsider3")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Outsider tries to review
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token3}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id1,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_review_self(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_host4")
    token2, user_id2 = await _register_and_get_token(client, "rev_join4")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id1,
            "skill_rating": 5,
            "punctuality_rating": 5,
            "sportsmanship_rating": 5,
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_submit_review_duplicate(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_host5")
    token2, user_id2 = await _register_and_get_token(client, "rev_join5")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    review_body = {
        "booking_id": booking_id,
        "reviewee_id": user_id2,
        "skill_rating": 4,
        "punctuality_rating": 4,
        "sportsmanship_rating": 4,
    }
    await client.post("/api/v1/reviews", headers={"Authorization": f"Bearer {token1}"}, json=review_body)
    resp = await client.post("/api/v1/reviews", headers={"Authorization": f"Bearer {token1}"}, json=review_body)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_submit_review_window_expired(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_host6")
    token2, user_id2 = await _register_and_get_token(client, "rev_join6")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Backdate the booking's updated_at to >24h ago so the window is expired
    from app.models.booking import Booking
    from sqlalchemy import update
    from datetime import datetime, timezone
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(updated_at=datetime.now(timezone.utc) - timedelta(hours=25))
    )
    await session.commit()

    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reviews.py -v`
Expected: All tests FAIL (no `/api/v1/reviews` endpoint yet).

- [ ] **Step 3: Create review service**

Create `app/services/review.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.review import Review
from app.models.user import User

REVIEW_WINDOW_HOURS = 24


def _is_within_review_window(booking: Booking) -> bool:
    """Check if the current time is within 24h of booking completion."""
    if booking.updated_at is None:
        return False
    deadline = booking.updated_at + timedelta(hours=REVIEW_WINDOW_HOURS)
    return datetime.now(timezone.utc) <= deadline


def _is_accepted_participant(booking: Booking, user_id: uuid.UUID) -> bool:
    """Check if user is an accepted participant in the booking."""
    return any(
        p.user_id == user_id and p.status == ParticipantStatus.ACCEPTED
        for p in booking.participants
    )


async def _get_booking_with_participants(session: AsyncSession, booking_id: uuid.UUID) -> Booking | None:
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.participants))
        .where(Booking.id == booking_id)
    )
    return result.scalar_one_or_none()


async def get_reverse_review(session: AsyncSession, booking_id: uuid.UUID, reviewer_id: uuid.UUID, reviewee_id: uuid.UUID) -> Review | None:
    """Check if the reverse review exists (reviewee reviewed the reviewer)."""
    result = await session.execute(
        select(Review).where(
            Review.booking_id == booking_id,
            Review.reviewer_id == reviewee_id,
            Review.reviewee_id == reviewer_id,
        )
    )
    return result.scalar_one_or_none()


async def submit_review(
    session: AsyncSession,
    *,
    booking_id: uuid.UUID,
    reviewer: User,
    reviewee_id: uuid.UUID,
    skill_rating: int,
    punctuality_rating: int,
    sportsmanship_rating: int,
    comment: str | None = None,
    lang: str = "en",
) -> tuple[Review, bool]:
    """Submit a review. Returns (review, is_revealed)."""
    from app.i18n import t

    # Load booking with participants
    booking = await _get_booking_with_participants(session, booking_id)
    if booking is None:
        raise ValueError(t("booking.not_found", lang))

    if booking.status != BookingStatus.COMPLETED:
        raise ValueError(t("review.booking_not_completed", lang))

    if reviewer.id == reviewee_id:
        raise ValueError(t("review.cannot_review_self", lang))

    if not _is_accepted_participant(booking, reviewer.id):
        raise PermissionError(t("review.not_participant", lang))

    if not _is_accepted_participant(booking, reviewee_id):
        raise ValueError(t("review.not_participant", lang))

    if not _is_within_review_window(booking):
        raise ValueError(t("review.window_expired", lang))

    # Check duplicate
    existing = await session.execute(
        select(Review).where(
            Review.booking_id == booking_id,
            Review.reviewer_id == reviewer.id,
            Review.reviewee_id == reviewee_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError(t("review.already_submitted", lang))

    review = Review(
        booking_id=booking_id,
        reviewer_id=reviewer.id,
        reviewee_id=reviewee_id,
        skill_rating=skill_rating,
        punctuality_rating=punctuality_rating,
        sportsmanship_rating=sportsmanship_rating,
        comment=comment,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)

    # Check if reverse review exists (for reveal status)
    reverse = await get_reverse_review(session, booking_id, reviewer.id, reviewee_id)
    is_revealed = reverse is not None

    return review, is_revealed


async def get_revealed_reviews_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[Review]:
    """Get all revealed, non-hidden reviews where user is the reviewee."""
    # A review is revealed if the reverse review exists
    reverse_alias = Review.__table__.alias("reverse_review")
    result = await session.execute(
        select(Review)
        .options(selectinload(Review.reviewer))
        .where(
            Review.reviewee_id == user_id,
            Review.is_hidden == False,
        )
        .where(
            select(reverse_alias.c.id)
            .where(
                reverse_alias.c.booking_id == Review.booking_id,
                reverse_alias.c.reviewer_id == Review.reviewee_id,
                reverse_alias.c.reviewee_id == Review.reviewer_id,
            )
            .correlate(Review.__table__)
            .exists()
        )
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


async def get_review_averages(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """Get average ratings for a user (only from revealed reviews)."""
    reverse_alias = Review.__table__.alias("reverse_review")
    result = await session.execute(
        select(
            func.avg(Review.skill_rating),
            func.avg(Review.punctuality_rating),
            func.avg(Review.sportsmanship_rating),
            func.count(Review.id),
        )
        .where(
            Review.reviewee_id == user_id,
            Review.is_hidden == False,
        )
        .where(
            select(reverse_alias.c.id)
            .where(
                reverse_alias.c.booking_id == Review.booking_id,
                reverse_alias.c.reviewer_id == Review.reviewee_id,
                reverse_alias.c.reviewee_id == Review.reviewer_id,
            )
            .correlate(Review.__table__)
            .exists()
        )
    )
    row = result.one()
    return {
        "average_skill": round(float(row[0]), 1) if row[0] else 0.0,
        "average_punctuality": round(float(row[1]), 1) if row[1] else 0.0,
        "average_sportsmanship": round(float(row[2]), 1) if row[2] else 0.0,
        "total_reviews": row[3],
    }


async def get_booking_reviews_for_user(session: AsyncSession, booking_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    """Get reviews for a booking relevant to the current user.

    Returns reviews where:
    - User is the reviewer (always visible, marked is_revealed based on reverse existence)
    - User is the reviewee AND reverse review exists (revealed)
    """
    all_reviews_result = await session.execute(
        select(Review)
        .options(selectinload(Review.reviewer))
        .where(Review.booking_id == booking_id)
        .where(
            (Review.reviewer_id == user_id) | (Review.reviewee_id == user_id)
        )
    )
    all_reviews = list(all_reviews_result.scalars().all())

    result = []
    for review in all_reviews:
        reverse = await get_reverse_review(session, booking_id, review.reviewer_id, review.reviewee_id)
        is_revealed = reverse is not None

        if review.reviewer_id == user_id:
            # Always show own reviews
            result.append({"review": review, "is_revealed": is_revealed})
        elif review.reviewee_id == user_id and is_revealed:
            # Show reviews about me only if revealed
            result.append({"review": review, "is_revealed": True})

    return result


async def get_pending_reviews(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Get bookings where user has pending reviews to submit.

    Returns completed bookings within 24h window where user hasn't reviewed all co-participants.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=REVIEW_WINDOW_HOURS)

    # Get completed bookings where user is accepted participant and within window
    bookings_result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.participants).selectinload(BookingParticipant.user),
            selectinload(Booking.court),
        )
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            Booking.status == BookingStatus.COMPLETED,
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.updated_at >= window_start,
        )
    )
    bookings = list(bookings_result.scalars().all())

    # For each booking, find co-participants not yet reviewed
    pending = []
    for booking in bookings:
        # Get already-submitted reviews by this user for this booking
        submitted_result = await session.execute(
            select(Review.reviewee_id).where(
                Review.booking_id == booking.id,
                Review.reviewer_id == user_id,
            )
        )
        already_reviewed = set(submitted_result.scalars().all())

        # Find accepted co-participants not yet reviewed
        reviewees = []
        for p in booking.participants:
            if p.user_id != user_id and p.status == ParticipantStatus.ACCEPTED and p.user_id not in already_reviewed:
                reviewees.append({"user_id": str(p.user_id), "nickname": p.user.nickname})

        if reviewees:
            window_closes = booking.updated_at + timedelta(hours=REVIEW_WINDOW_HOURS)
            pending.append({
                "booking_id": str(booking.id),
                "court_name": booking.court.name,
                "play_date": booking.play_date.isoformat(),
                "reviewees": reviewees,
                "window_closes_at": window_closes.isoformat(),
            })

    return pending
```

- [ ] **Step 4: Run tests to verify they still fail (service exists but no router yet)**

Run: `uv run pytest tests/test_reviews.py -v`
Expected: All tests still FAIL (405 Method Not Allowed — no route registered).

- [ ] **Step 5: Commit service**

```bash
git add app/services/review.py
git commit -m "feat: add review service with submit, blind reveal, and pending logic"
```

---

### Task 5: Review Router + Wire Up

**Files:**
- Create: `app/routers/reviews.py`
- Modify: `app/main.py`

- [ ] **Step 1: Create review router**

Create `app/routers/reviews.py`:

```python
from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.review import (
    ReviewCreateRequest,
    ReviewResponse,
    UserReviewSummary,
)
from app.services.review import (
    get_booking_reviews_for_user,
    get_pending_reviews,
    get_review_averages,
    get_revealed_reviews_for_user,
    submit_review,
)

router = APIRouter()


def _review_to_response(review, is_revealed: bool) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        booking_id=review.booking_id,
        reviewer_id=review.reviewer_id,
        reviewee_id=review.reviewee_id,
        reviewer_nickname=review.reviewer.nickname,
        skill_rating=review.skill_rating,
        punctuality_rating=review.punctuality_rating,
        sportsmanship_rating=review.sportsmanship_rating,
        comment=review.comment,
        is_revealed=is_revealed,
        created_at=review.created_at,
    )


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(body: ReviewCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        review, is_revealed = await submit_review(
            session,
            booking_id=body.booking_id,
            reviewer=user,
            reviewee_id=body.reviewee_id,
            skill_rating=body.skill_rating,
            punctuality_rating=body.punctuality_rating,
            sportsmanship_rating=body.sportsmanship_rating,
            comment=body.comment,
            lang=lang,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Reload review with reviewer relationship for nickname
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.review import Review
    result = await session.execute(
        select(Review).options(selectinload(Review.reviewer)).where(Review.id == review.id)
    )
    review = result.scalar_one()

    return _review_to_response(review, is_revealed)


@router.get("/pending")
async def get_my_pending_reviews(user: CurrentUser, session: DbSession):
    return await get_pending_reviews(session, user.id)


@router.get("/users/{user_id}", response_model=UserReviewSummary)
async def get_user_reviews(user_id: str, session: DbSession):
    import uuid
    uid = uuid.UUID(user_id)
    reviews = await get_revealed_reviews_for_user(session, uid)
    averages = await get_review_averages(session, uid)

    return UserReviewSummary(
        average_skill=averages["average_skill"],
        average_punctuality=averages["average_punctuality"],
        average_sportsmanship=averages["average_sportsmanship"],
        total_reviews=averages["total_reviews"],
        reviews=[_review_to_response(r, is_revealed=True) for r in reviews],
    )


@router.get("/bookings/{booking_id}")
async def get_booking_reviews(booking_id: str, user: CurrentUser, session: DbSession):
    import uuid
    results = await get_booking_reviews_for_user(session, uuid.UUID(booking_id), user.id)
    return [_review_to_response(item["review"], item["is_revealed"]) for item in results]
```

- [ ] **Step 2: Register router in app factory**

Add to `app/main.py` in `create_app()`, after the bookings router import and registration:

```python
    from app.routers import auth, bookings, courts, reviews, users

    # ... existing routers ...
    app.include_router(reviews.router, prefix="/api/v1/reviews", tags=["reviews"])
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_reviews.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/routers/reviews.py app/main.py
git commit -m "feat: add review router and register in app factory"
```

---

### Task 6: Blind Reveal Tests

**Files:**
- Modify: `tests/test_reviews.py`

- [ ] **Step 1: Write blind reveal tests**

Add to `tests/test_reviews.py`:

```python
# --- Blind Reveal Tests ---


@pytest.mark.asyncio
async def test_blind_reveal_single_side_not_visible(client: AsyncClient, session: AsyncSession):
    """When only one side reviews, the other side cannot see it."""
    token1, user_id1 = await _register_and_get_token(client, "blind_host1")
    token2, user_id2 = await _register_and_get_token(client, "blind_join1")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Only user1 reviews user2
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 4,
        },
    )

    # User2's public profile should show no reviews (not revealed)
    resp = await client.get(f"/api/v1/reviews/users/{user_id2}")
    assert resp.status_code == 200
    assert resp.json()["total_reviews"] == 0
    assert len(resp.json()["reviews"]) == 0


@pytest.mark.asyncio
async def test_blind_reveal_both_sides_visible(client: AsyncClient, session: AsyncSession):
    """When both sides review each other, both reviews become visible."""
    token1, user_id1 = await _register_and_get_token(client, "blind_host2")
    token2, user_id2 = await _register_and_get_token(client, "blind_join2")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # User1 reviews user2
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 4,
        },
    )

    # User2 reviews user1
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id1,
            "skill_rating": 3,
            "punctuality_rating": 4,
            "sportsmanship_rating": 5,
        },
    )

    # Now user2's profile should show the revealed review
    resp = await client.get(f"/api/v1/reviews/users/{user_id2}")
    assert resp.status_code == 200
    assert resp.json()["total_reviews"] == 1
    assert resp.json()["average_skill"] == 4.0

    # User1's profile should also show the revealed review
    resp = await client.get(f"/api/v1/reviews/users/{user_id1}")
    assert resp.status_code == 200
    assert resp.json()["total_reviews"] == 1
    assert resp.json()["average_skill"] == 3.0


@pytest.mark.asyncio
async def test_reviewer_sees_own_review(client: AsyncClient, session: AsyncSession):
    """Reviewer can see their own submitted review in booking reviews."""
    token1, user_id1 = await _register_and_get_token(client, "blind_host3")
    token2, user_id2 = await _register_and_get_token(client, "blind_join3")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Only user1 reviews
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 4,
        },
    )

    # User1 can see their own review in booking reviews
    resp = await client.get(
        f"/api/v1/reviews/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["reviewer_id"] == user_id1
    assert resp.json()[0]["is_revealed"] is False

    # User2 cannot see the review (not revealed)
    resp = await client.get(
        f"/api/v1/reviews/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_reviews.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_reviews.py
git commit -m "test: add blind reveal tests for review system"
```

---

### Task 7: Pending Reviews + User Profile Averages Tests

**Files:**
- Modify: `tests/test_reviews.py`

- [ ] **Step 1: Write pending reviews and averages tests**

Add to `tests/test_reviews.py`:

```python
# --- Pending Reviews Tests ---


@pytest.mark.asyncio
async def test_pending_reviews_shows_unreviewd(client: AsyncClient, session: AsyncSession):
    """Pending endpoint shows bookings where user hasn't reviewed co-participants."""
    token1, user_id1 = await _register_and_get_token(client, "pend_host1")
    token2, user_id2 = await _register_and_get_token(client, "pend_join1")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    resp = await client.get("/api/v1/reviews/pending", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["booking_id"] == booking_id
    assert len(data[0]["reviewees"]) == 1
    assert data[0]["reviewees"][0]["user_id"] == user_id2


@pytest.mark.asyncio
async def test_pending_reviews_excludes_already_reviewed(client: AsyncClient, session: AsyncSession):
    """After reviewing all co-participants, booking no longer appears in pending."""
    token1, user_id1 = await _register_and_get_token(client, "pend_host2")
    token2, user_id2 = await _register_and_get_token(client, "pend_join2")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Submit review
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 4,
        },
    )

    resp = await client.get("/api/v1/reviews/pending", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_pending_reviews_excludes_expired_window(client: AsyncClient, session: AsyncSession):
    """Bookings past the 24h window don't appear in pending."""
    token1, user_id1 = await _register_and_get_token(client, "pend_host3")
    token2, user_id2 = await _register_and_get_token(client, "pend_join3")
    court = await _seed_court(session)
    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Backdate updated_at past window
    from app.models.booking import Booking
    from sqlalchemy import update
    from datetime import datetime, timezone
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(updated_at=datetime.now(timezone.utc) - timedelta(hours=25))
    )
    await session.commit()

    resp = await client.get("/api/v1/reviews/pending", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 0


# --- User Review Summary Tests ---


@pytest.mark.asyncio
async def test_user_reviews_empty(client: AsyncClient, session: AsyncSession):
    """User with no reviews returns zero averages."""
    token1, user_id1 = await _register_and_get_token(client, "empty_rev1")

    resp = await client.get(f"/api/v1/reviews/users/{user_id1}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 0
    assert data["average_skill"] == 0.0
    assert data["average_punctuality"] == 0.0
    assert data["average_sportsmanship"] == 0.0
    assert data["reviews"] == []


@pytest.mark.asyncio
async def test_user_reviews_averages_correct(client: AsyncClient, session: AsyncSession):
    """Averages are computed correctly from multiple revealed reviews."""
    token1, user_id1 = await _register_and_get_token(client, "avg_host1")
    token2, user_id2 = await _register_and_get_token(client, "avg_join1")
    token3, user_id3 = await _register_and_get_token(client, "avg_join2")
    court = await _seed_court(session)

    # Complete booking between user1 and user2
    booking_id1 = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Both review each other (to reveal)
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token2}"},
        json={"booking_id": booking_id1, "reviewee_id": user_id1, "skill_rating": 4, "punctuality_rating": 4, "sportsmanship_rating": 4},
    )
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={"booking_id": booking_id1, "reviewee_id": user_id2, "skill_rating": 5, "punctuality_rating": 5, "sportsmanship_rating": 5},
    )

    # Complete booking between user1 and user3
    booking_id2 = await _create_completed_booking(client, session, token1, token3, str(court.id))

    # Both review each other
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token3}"},
        json={"booking_id": booking_id2, "reviewee_id": user_id1, "skill_rating": 2, "punctuality_rating": 4, "sportsmanship_rating": 4},
    )
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={"booking_id": booking_id2, "reviewee_id": user_id3, "skill_rating": 3, "punctuality_rating": 3, "sportsmanship_rating": 3},
    )

    # Check user1's averages: skill=(4+2)/2=3.0, punctuality=(4+4)/2=4.0, sportsmanship=(4+4)/2=4.0
    resp = await client.get(f"/api/v1/reviews/users/{user_id1}")
    data = resp.json()
    assert data["total_reviews"] == 2
    assert data["average_skill"] == 3.0
    assert data["average_punctuality"] == 4.0
    assert data["average_sportsmanship"] == 4.0
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/test_reviews.py -v`
Expected: All 14 tests PASS.

- [ ] **Step 3: Run full test suite to check for regressions**

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS alongside the new review tests.

- [ ] **Step 4: Commit**

```bash
git add tests/test_reviews.py
git commit -m "test: add pending reviews and user averages tests"
```
