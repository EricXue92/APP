# Playing Statistics & Calendar View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add public playing statistics and a month-based calendar view to user profiles, computed at query time from existing booking data.

**Architecture:** Two new GET endpoints under `/api/v1/users/{user_id}/`, backed by a new `stats.py` service that aggregates data from `BookingParticipant` + `Booking` tables. No new database tables or migrations needed.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest + httpx

---

### Task 1: Create schemas

**Files:**

- Create: `app/schemas/stats.py`

- [ ] **Step 1: Create the schema file**

```python
import uuid
from datetime import date

from pydantic import BaseModel


class CourtStats(BaseModel):
    court_id: uuid.UUID
    court_name: str
    match_count: int

    model_config = {"from_attributes": True}


class PartnerStats(BaseModel):
    user_id: uuid.UUID
    nickname: str
    avatar_url: str | None
    match_count: int

    model_config = {"from_attributes": True}


class UserStats(BaseModel):
    total_matches: int
    monthly_matches: int
    singles_count: int
    doubles_count: int
    top_courts: list[CourtStats]
    top_partners: list[PartnerStats]

    model_config = {"from_attributes": True}


class CalendarParticipant(BaseModel):
    user_id: uuid.UUID
    nickname: str

    model_config = {"from_attributes": True}


class CalendarBooking(BaseModel):
    booking_id: uuid.UUID
    court_name: str
    match_type: str
    start_time: str
    end_time: str
    participants: list[CalendarParticipant]

    model_config = {"from_attributes": True}


class CalendarDate(BaseModel):
    date: date
    bookings: list[CalendarBooking]

    model_config = {"from_attributes": True}


class UserCalendar(BaseModel):
    year: int
    month: int
    match_dates: list[CalendarDate]

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Verify the file imports cleanly**

Run: `uv run python -c "from app.schemas.stats import UserStats, UserCalendar; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/stats.py
git commit -m "feat(stats): add schemas for playing statistics and calendar"
```

---

### Task 2: Create stats service — `get_user_stats`

**Files:**

- Create: `app/services/stats.py`
- Test: `tests/test_stats.py`

- [ ] **Step 1: Write failing tests for `get_user_stats`**

Create `tests/test_stats.py`:

```python
import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, MatchType, ParticipantStatus
from app.models.court import Court, CourtType
from app.models.user import User


async def _register_and_get_token(client: AsyncClient, username: str, ntrp: str = "3.5") -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": ntrp,
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


async def _seed_court(session: AsyncSession, name: str = "Test Court") -> Court:
    court = Court(
        name=name,
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _seed_completed_booking(
    session: AsyncSession,
    court: Court,
    user_ids: list[uuid.UUID],
    play_date: date | None = None,
    match_type: MatchType = MatchType.SINGLES,
) -> Booking:
    """Create a completed booking with accepted participants."""
    booking = Booking(
        creator_id=user_ids[0],
        court_id=court.id,
        match_type=match_type,
        play_date=play_date or date.today(),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        max_participants=2 if match_type == MatchType.SINGLES else 4,
        status=BookingStatus.COMPLETED,
    )
    session.add(booking)
    await session.flush()

    for uid in user_ids:
        participant = BookingParticipant(
            booking_id=booking.id,
            user_id=uid,
            status=ParticipantStatus.ACCEPTED,
        )
        session.add(participant)

    await session.commit()
    await session.refresh(booking)
    return booking


# --- Stats endpoint tests ---


@pytest.mark.asyncio
async def test_stats_no_matches(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "lonely")
    resp = await client.get(
        f"/api/v1/users/{user_id}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_matches"] == 0
    assert data["monthly_matches"] == 0
    assert data["singles_count"] == 0
    assert data["doubles_count"] == 0
    assert data["top_courts"] == []
    assert data["top_partners"] == []


@pytest.mark.asyncio
async def test_stats_with_completed_matches(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "alice")
    _, uid_b = await _register_and_get_token(client, "bob")
    court = await _seed_court(session)

    await _seed_completed_booking(session, court, [uuid.UUID(uid_a), uuid.UUID(uid_b)])
    await _seed_completed_booking(
        session, court, [uuid.UUID(uid_a), uuid.UUID(uid_b)], match_type=MatchType.DOUBLES
    )

    resp = await client.get(
        f"/api/v1/users/{uid_a}/stats",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_matches"] == 2
    assert data["singles_count"] == 1
    assert data["doubles_count"] == 1


@pytest.mark.asyncio
async def test_stats_top_courts_ranking(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "courtfan")
    _, uid_b = await _register_and_get_token(client, "partner1")
    court_a = await _seed_court(session, "Court Alpha")
    court_b = await _seed_court(session, "Court Beta")
    court_c = await _seed_court(session, "Court Gamma")
    court_d = await _seed_court(session, "Court Delta")

    uids = [uuid.UUID(uid), uuid.UUID(uid_b)]
    # Court Alpha: 3 matches, Court Beta: 2, Court Gamma: 1, Court Delta: 1
    for _ in range(3):
        await _seed_completed_booking(session, court_a, uids)
    for _ in range(2):
        await _seed_completed_booking(session, court_b, uids)
    await _seed_completed_booking(session, court_c, uids)
    await _seed_completed_booking(session, court_d, uids)

    resp = await client.get(
        f"/api/v1/users/{uid}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    courts = data["top_courts"]
    assert len(courts) == 3
    assert courts[0]["court_name"] == "Court Alpha"
    assert courts[0]["match_count"] == 3
    assert courts[1]["court_name"] == "Court Beta"
    assert courts[1]["match_count"] == 2


@pytest.mark.asyncio
async def test_stats_top_partners_ranking(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "social")
    _, uid_b = await _register_and_get_token(client, "freq_partner")
    _, uid_c = await _register_and_get_token(client, "rare_partner")
    court = await _seed_court(session)

    # freq_partner: 3 matches, rare_partner: 1 match
    for _ in range(3):
        await _seed_completed_booking(session, court, [uuid.UUID(uid), uuid.UUID(uid_b)])
    await _seed_completed_booking(session, court, [uuid.UUID(uid), uuid.UUID(uid_c)])

    resp = await client.get(
        f"/api/v1/users/{uid}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    partners = data["top_partners"]
    assert len(partners) == 2
    assert partners[0]["nickname"] == "Player_freq_partner"
    assert partners[0]["match_count"] == 3
    assert partners[1]["nickname"] == "Player_rare_partner"
    assert partners[1]["match_count"] == 1
    # Ensure self is not in partners list
    partner_ids = [p["user_id"] for p in partners]
    assert uid not in partner_ids


@pytest.mark.asyncio
async def test_stats_monthly_matches(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "monthly")
    _, uid_b = await _register_and_get_token(client, "monthly_b")
    court = await _seed_court(session)
    uids = [uuid.UUID(uid), uuid.UUID(uid_b)]

    # One match this month, one match last month
    await _seed_completed_booking(session, court, uids, play_date=date.today())
    last_month = date.today().replace(day=1) - timedelta(days=1)
    await _seed_completed_booking(session, court, uids, play_date=last_month)

    resp = await client.get(
        f"/api/v1/users/{uid}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert data["total_matches"] == 2
    assert data["monthly_matches"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_stats.py -v`
Expected: FAIL (404 — routes don't exist yet)

- [ ] **Step 3: Write `get_user_stats` service**

Create `app/services/stats.py`:

```python
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import (
    Booking,
    BookingParticipant,
    BookingStatus,
    MatchType,
    ParticipantStatus,
)
from app.models.court import Court
from app.models.user import User


async def get_user_stats(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """Compute playing statistics for a user from completed bookings."""
    # Base condition: user participated and was accepted, booking was completed
    base_join = (
        select(Booking.id)
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
    )

    # 1. total_matches
    total_q = select(func.count()).select_from(base_join.subquery())
    total_matches = (await session.execute(total_q)).scalar() or 0

    # 2. monthly_matches (current calendar month)
    today = date.today()
    monthly_q = select(func.count()).select_from(
        base_join.where(
            func.extract("year", Booking.play_date) == today.year,
            func.extract("month", Booking.play_date) == today.month,
        ).subquery()
    )
    monthly_matches = (await session.execute(monthly_q)).scalar() or 0

    # 3. singles_count / doubles_count
    type_q = (
        select(Booking.match_type, func.count())
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
        .group_by(Booking.match_type)
    )
    type_rows = (await session.execute(type_q)).all()
    type_counts = {row[0]: row[1] for row in type_rows}
    singles_count = type_counts.get(MatchType.SINGLES, 0)
    doubles_count = type_counts.get(MatchType.DOUBLES, 0)

    # 4. top_courts (top 3)
    court_q = (
        select(Court.id, Court.name, func.count().label("cnt"))
        .join(Booking, Booking.court_id == Court.id)
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
        .group_by(Court.id, Court.name)
        .order_by(func.count().desc())
        .limit(3)
    )
    court_rows = (await session.execute(court_q)).all()
    top_courts = [
        {"court_id": row[0], "court_name": row[1], "match_count": row[2]}
        for row in court_rows
    ]

    # 5. top_partners (top 3, excluding self)
    # Find other participants in the same completed bookings
    user_bookings = (
        select(BookingParticipant.booking_id)
        .join(Booking, Booking.id == BookingParticipant.booking_id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
        .scalar_subquery()
    )
    partner_q = (
        select(User.id, User.nickname, User.avatar_url, func.count().label("cnt"))
        .join(BookingParticipant, BookingParticipant.user_id == User.id)
        .where(
            BookingParticipant.booking_id.in_(user_bookings),
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            BookingParticipant.user_id != user_id,
        )
        .group_by(User.id, User.nickname, User.avatar_url)
        .order_by(func.count().desc())
        .limit(3)
    )
    partner_rows = (await session.execute(partner_q)).all()
    top_partners = [
        {
            "user_id": row[0],
            "nickname": row[1],
            "avatar_url": row[2],
            "match_count": row[3],
        }
        for row in partner_rows
    ]

    return {
        "total_matches": total_matches,
        "monthly_matches": monthly_matches,
        "singles_count": singles_count,
        "doubles_count": doubles_count,
        "top_courts": top_courts,
        "top_partners": top_partners,
    }
```

- [ ] **Step 4: Add routes to users router**

Modify `app/routers/users.py` — add the stats endpoint:

```python
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.stats import UserStats
from app.schemas.user import UserProfileResponse, UserUpdateRequest
from app.services.block import is_blocked
from app.services.stats import get_user_stats
from app.services.user import update_user

router = APIRouter()


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(body: UserUpdateRequest, user: CurrentUser, session: DbSession):
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return user
    updated = await update_user(session, user, **update_data)
    return updated


@router.get("/{user_id}/stats", response_model=UserStats)
async def get_stats(user_id: uuid.UUID, user: CurrentUser, session: DbSession):
    if await is_blocked(session, user.id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    result = await get_user_stats(session, user_id)
    return result
```

- [ ] **Step 5: Run stats tests to verify they pass**

Run: `uv run pytest tests/test_stats.py -v`
Expected: All stats tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/stats.py app/routers/users.py tests/test_stats.py
git commit -m "feat(stats): add user playing statistics endpoint with tests"
```

---

### Task 3: Create calendar service — `get_user_calendar`

**Files:**

- Modify: `app/services/stats.py`
- Modify: `app/routers/users.py`
- Modify: `tests/test_stats.py`

- [ ] **Step 1: Write failing tests for calendar endpoint**

Append to `tests/test_stats.py`:

```python
from app.models.booking import GenderRequirement


# --- Calendar endpoint tests ---


@pytest.mark.asyncio
async def test_calendar_correct_dates(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "cal_user")
    _, uid_b = await _register_and_get_token(client, "cal_partner")
    court = await _seed_court(session, "Calendar Court")
    uids = [uuid.UUID(uid), uuid.UUID(uid_b)]
    today = date.today()

    await _seed_completed_booking(session, court, uids, play_date=today)

    resp = await client.get(
        f"/api/v1/users/{uid}/calendar",
        params={"year": today.year, "month": today.month},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["year"] == today.year
    assert data["month"] == today.month
    assert len(data["match_dates"]) == 1
    match_date = data["match_dates"][0]
    assert match_date["date"] == today.isoformat()
    assert len(match_date["bookings"]) == 1
    booking = match_date["bookings"][0]
    assert booking["court_name"] == "Calendar Court"
    assert booking["match_type"] == "singles"
    # Participants should exclude the target user
    participant_ids = [p["user_id"] for p in booking["participants"]]
    assert uid not in participant_ids
    assert uid_b in participant_ids


@pytest.mark.asyncio
async def test_calendar_excludes_non_completed(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "noncomplete")
    _, uid_b = await _register_and_get_token(client, "noncomplete_b")
    court = await _seed_court(session)
    today = date.today()

    # Create an open (not completed) booking
    booking = Booking(
        creator_id=uuid.UUID(uid),
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=today,
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        max_participants=2,
        status=BookingStatus.OPEN,
    )
    session.add(booking)
    await session.flush()
    session.add(BookingParticipant(
        booking_id=booking.id, user_id=uuid.UUID(uid), status=ParticipantStatus.ACCEPTED
    ))
    await session.commit()

    resp = await client.get(
        f"/api/v1/users/{uid}/calendar",
        params={"year": today.year, "month": today.month},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["match_dates"]) == 0


@pytest.mark.asyncio
async def test_calendar_excludes_rejected_participants(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "rejected_user")
    _, uid_b = await _register_and_get_token(client, "rejected_b")
    court = await _seed_court(session)
    today = date.today()

    # Create a completed booking where user was rejected
    booking = Booking(
        creator_id=uuid.UUID(uid_b),
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=today,
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        max_participants=2,
        status=BookingStatus.COMPLETED,
    )
    session.add(booking)
    await session.flush()
    session.add(BookingParticipant(
        booking_id=booking.id, user_id=uuid.UUID(uid), status=ParticipantStatus.REJECTED
    ))
    session.add(BookingParticipant(
        booking_id=booking.id, user_id=uuid.UUID(uid_b), status=ParticipantStatus.ACCEPTED
    ))
    await session.commit()

    resp = await client.get(
        f"/api/v1/users/{uid}/calendar",
        params={"year": today.year, "month": today.month},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # User was rejected, so no match dates for them
    assert len(resp.json()["match_dates"]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_stats.py::test_calendar_correct_dates tests/test_stats.py::test_calendar_excludes_non_completed tests/test_stats.py::test_calendar_excludes_rejected_participants -v`
Expected: FAIL (404 — calendar route doesn't exist yet)

- [ ] **Step 3: Add `get_user_calendar` to the service**

Append to `app/services/stats.py`:

```python
from collections import defaultdict


async def get_user_calendar(
    session: AsyncSession, user_id: uuid.UUID, year: int, month: int
) -> dict:
    """Return completed match dates for a user in a given month."""
    # Query completed bookings where user was accepted participant in the given month
    q = (
        select(
            Booking.id,
            Booking.play_date,
            Booking.match_type,
            Booking.start_time,
            Booking.end_time,
            Court.name.label("court_name"),
        )
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .join(Court, Court.id == Booking.court_id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
            func.extract("year", Booking.play_date) == year,
            func.extract("month", Booking.play_date) == month,
        )
        .order_by(Booking.play_date, Booking.start_time)
    )
    rows = (await session.execute(q)).all()

    # Collect booking IDs to fetch other participants
    booking_ids = [row[0] for row in rows]

    # Fetch other accepted participants for these bookings (excluding target user)
    participants_by_booking: dict[uuid.UUID, list[dict]] = defaultdict(list)
    if booking_ids:
        p_q = (
            select(
                BookingParticipant.booking_id,
                User.id,
                User.nickname,
            )
            .join(User, User.id == BookingParticipant.user_id)
            .where(
                BookingParticipant.booking_id.in_(booking_ids),
                BookingParticipant.status == ParticipantStatus.ACCEPTED,
                BookingParticipant.user_id != user_id,
            )
        )
        p_rows = (await session.execute(p_q)).all()
        for p_row in p_rows:
            participants_by_booking[p_row[0]].append(
                {"user_id": p_row[1], "nickname": p_row[2]}
            )

    # Group by date
    dates_map: dict[date, list[dict]] = defaultdict(list)
    for row in rows:
        booking_id, play_date, match_type, start_time, end_time, court_name = row
        dates_map[play_date].append(
            {
                "booking_id": booking_id,
                "court_name": court_name,
                "match_type": match_type.value,
                "start_time": start_time.strftime("%H:%M"),
                "end_time": end_time.strftime("%H:%M"),
                "participants": participants_by_booking.get(booking_id, []),
            }
        )

    match_dates = [
        {"date": d, "bookings": bookings}
        for d, bookings in sorted(dates_map.items())
    ]

    return {"year": year, "month": month, "match_dates": match_dates}
```

- [ ] **Step 4: Add calendar route to users router**

Add to `app/routers/users.py` after the stats route:

```python
from app.schemas.stats import UserCalendar
from app.services.stats import get_user_calendar

@router.get("/{user_id}/calendar", response_model=UserCalendar)
async def get_calendar(
    user_id: uuid.UUID,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    user: CurrentUser,
    session: DbSession,
):
    if await is_blocked(session, user.id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    result = await get_user_calendar(session, user_id, year, month)
    return result
```

Note: the `Query` import was already added in Task 2. The `UserCalendar` and `get_user_calendar` imports are new.

- [ ] **Step 5: Run calendar tests to verify they pass**

Run: `uv run pytest tests/test_stats.py -v`
Expected: All tests PASS (stats + calendar)

- [ ] **Step 6: Commit**

```bash
git add app/services/stats.py app/routers/users.py tests/test_stats.py
git commit -m "feat(stats): add calendar view endpoint with tests"
```

---

### Task 4: Add block check and auth tests

**Files:**

- Modify: `tests/test_stats.py`

- [ ] **Step 1: Write block and auth tests**

Append to `tests/test_stats.py`:

```python
from app.models.block import Block


# --- Block and auth tests ---


@pytest.mark.asyncio
async def test_stats_blocked_user_returns_404(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "blocker")
    _, uid_b = await _register_and_get_token(client, "blocked")

    # Create block: A blocks B
    block = Block(blocker_id=uuid.UUID(uid_a), blocked_id=uuid.UUID(uid_b))
    session.add(block)
    await session.commit()

    # A tries to view B's stats
    resp = await client.get(
        f"/api/v1/users/{uid_b}/stats",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_calendar_blocked_user_returns_404(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "cal_blocker")
    _, uid_b = await _register_and_get_token(client, "cal_blocked")

    block = Block(blocker_id=uuid.UUID(uid_a), blocked_id=uuid.UUID(uid_b))
    session.add(block)
    await session.commit()

    today = date.today()
    resp = await client.get(
        f"/api/v1/users/{uid_b}/calendar",
        params={"year": today.year, "month": today.month},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stats_unauthenticated(client: AsyncClient):
    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}/stats")
    assert resp.status_code == 422 or resp.status_code == 401


@pytest.mark.asyncio
async def test_calendar_unauthenticated(client: AsyncClient):
    today = date.today()
    resp = await client.get(
        f"/api/v1/users/{uuid.uuid4()}/calendar",
        params={"year": today.year, "month": today.month},
    )
    assert resp.status_code == 422 or resp.status_code == 401
```

- [ ] **Step 2: Run all tests to verify they pass**

Run: `uv run pytest tests/test_stats.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_stats.py
git commit -m "test(stats): add block check and auth tests"
```

---

### Task 5: Full test suite verification

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ -v`
Expected: All 516+ tests PASS (existing tests unchanged, new stats tests added)

- [ ] **Step 2: Commit any fixes if needed**

If any existing tests broke (they shouldn't — we only added new routes and a new service), fix and commit.

- [ ] **Step 3: Final commit if clean**

```bash
git log --oneline -5
```

Verify 3 new commits from Tasks 1-4 are present.
