# User Search / Player Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a player directory endpoint (`GET /api/v1/users/search`) with filters for keyword, city, gender, NTRP range, court proximity, and ideal player status.

**Architecture:** Single search service builds a dynamic SQLAlchemy query with optional filters. Court proximity uses haversine (reused from matching module). `last_active_at` and `is_following` computed as subqueries at query time. Block/suspended/inactive users excluded. Router adds the endpoint to the existing users router.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL

---

## File Structure

| Action | File                          | Responsibility                                          |
| ------ | ----------------------------- | ------------------------------------------------------- |
| Create | `app/schemas/user_search.py`  | Request validation + response models                    |
| Create | `app/services/user_search.py` | Query builder with all filters, sorting, pagination     |
| Modify | `app/routers/users.py:1-12`   | Add `GET /search` endpoint (before `/{user_id}` routes) |
| Create | `tests/test_user_search.py`   | Integration tests                                       |

---

### Task 1: Schemas

**Files:**

- Create: `app/schemas/user_search.py`

- [ ] **Step 1: Create schema file**

Create `app/schemas/user_search.py`:

```python
import uuid
from datetime import date

from pydantic import BaseModel, Field


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

    model_config = {"from_attributes": True}


class UserSearchResponse(BaseModel):
    users: list[UserSearchItem]
    total: int
    page: int
    page_size: int

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/user_search.py
git commit -m "feat(search): add user search schemas"
```

---

### Task 2: Service Layer — Basic Filters

**Files:**

- Create: `app/services/user_search.py`
- Create: `tests/test_user_search.py`

- [ ] **Step 1: Write basic search tests**

Create `tests/test_user_search.py`:

```python
import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import (
    Booking,
    BookingParticipant,
    BookingStatus,
    MatchType,
    ParticipantStatus,
)
from app.models.block import Block
from app.models.court import Court, CourtType
from app.models.follow import Follow
from app.models.user import User


async def _register(client: AsyncClient, username: str, **kwargs) -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    params = {
        "nickname": kwargs.get("nickname", f"Player_{username}"),
        "gender": kwargs.get("gender", "male"),
        "city": kwargs.get("city", "Hong Kong"),
        "ntrp_level": kwargs.get("ntrp_level", "3.5"),
        "language": "en",
    }
    resp = await client.post(
        "/api/v1/auth/register/username",
        params=params,
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept-Language": "en"}


async def _seed_court(
    session: AsyncSession,
    name: str = "Test Court",
    lat: float | None = None,
    lng: float | None = None,
) -> Court:
    court = Court(
        name=name,
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
        latitude=lat,
        longitude=lng,
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
) -> Booking:
    booking = Booking(
        creator_id=user_ids[0],
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=play_date or date.today(),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="1.0",
        max_ntrp="7.0",
        max_participants=2,
        status=BookingStatus.COMPLETED,
    )
    session.add(booking)
    await session.flush()

    for uid in user_ids:
        session.add(BookingParticipant(
            booking_id=booking.id,
            user_id=uid,
            status=ParticipantStatus.ACCEPTED,
        ))

    await session.commit()
    await session.refresh(booking)
    return booking


# --- Basic search tests ---


@pytest.mark.asyncio
async def test_search_returns_users(client: AsyncClient, session: AsyncSession):
    """Basic search returns other users."""
    token_a, _ = await _register(client, "searcher")
    _, _ = await _register(client, "target")

    resp = await client.get("/api/v1/users/search", headers=_auth(token_a))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(u["nickname"] == "Player_target" for u in data["users"])


@pytest.mark.asyncio
async def test_search_excludes_caller(client: AsyncClient, session: AsyncSession):
    """Caller is not in their own search results."""
    token_a, _ = await _register(client, "self_searcher")

    resp = await client.get("/api/v1/users/search", headers=_auth(token_a))
    assert resp.status_code == 200
    assert all(u["nickname"] != "Player_self_searcher" for u in resp.json()["users"])


@pytest.mark.asyncio
async def test_search_excludes_blocked(client: AsyncClient, session: AsyncSession):
    """Blocked users excluded in both directions."""
    token_a, id_a = await _register(client, "blocker_s")
    _, id_b = await _register(client, "blocked_s")

    session.add(Block(blocker_id=uuid.UUID(id_a), blocked_id=uuid.UUID(id_b)))
    await session.commit()

    resp = await client.get("/api/v1/users/search", headers=_auth(token_a))
    assert all(u["nickname"] != "Player_blocked_s" for u in resp.json()["users"])


@pytest.mark.asyncio
async def test_search_excludes_suspended(client: AsyncClient, session: AsyncSession):
    """Suspended users are excluded."""
    token_a, _ = await _register(client, "active_s")
    _, id_b = await _register(client, "suspended_s")

    user_b = await session.get(User, uuid.UUID(id_b))
    user_b.is_suspended = True
    await session.commit()

    resp = await client.get("/api/v1/users/search", headers=_auth(token_a))
    assert all(u["nickname"] != "Player_suspended_s" for u in resp.json()["users"])


@pytest.mark.asyncio
async def test_search_keyword_filter(client: AsyncClient, session: AsyncSession):
    """Keyword filters by nickname (case-insensitive partial match)."""
    token_a, _ = await _register(client, "kw_searcher")
    _, _ = await _register(client, "kw_alice", nickname="Alice_Tennis")
    _, _ = await _register(client, "kw_bob", nickname="Bob_Ball")

    resp = await client.get(
        "/api/v1/users/search",
        params={"keyword": "alice"},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["total"] == 1
    assert data["users"][0]["nickname"] == "Alice_Tennis"


@pytest.mark.asyncio
async def test_search_city_filter(client: AsyncClient, session: AsyncSession):
    """City filter returns exact match only."""
    token_a, _ = await _register(client, "city_searcher", city="Hong Kong")
    _, _ = await _register(client, "city_hk", city="Hong Kong")
    _, _ = await _register(client, "city_tp", city="Taipei")

    resp = await client.get(
        "/api/v1/users/search",
        params={"city": "Taipei"},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["total"] == 1
    assert data["users"][0]["nickname"] == "Player_city_tp"


@pytest.mark.asyncio
async def test_search_gender_filter(client: AsyncClient, session: AsyncSession):
    """Gender filter returns matching gender only."""
    token_a, _ = await _register(client, "gender_searcher", gender="male")
    _, _ = await _register(client, "gender_m", gender="male")
    _, _ = await _register(client, "gender_f", gender="female")

    resp = await client.get(
        "/api/v1/users/search",
        params={"gender": "female"},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["total"] == 1
    assert data["users"][0]["nickname"] == "Player_gender_f"


@pytest.mark.asyncio
async def test_search_ntrp_range_filter(client: AsyncClient, session: AsyncSession):
    """NTRP range filter excludes users outside range."""
    token_a, _ = await _register(client, "ntrp_searcher", ntrp_level="3.5")
    _, _ = await _register(client, "ntrp_low", ntrp_level="2.0")
    _, _ = await _register(client, "ntrp_mid", ntrp_level="3.5")
    _, _ = await _register(client, "ntrp_high", ntrp_level="5.0")

    resp = await client.get(
        "/api/v1/users/search",
        params={"min_ntrp": "3.0", "max_ntrp": "4.0"},
        headers=_auth(token_a),
    )
    data = resp.json()
    nicknames = [u["nickname"] for u in data["users"]]
    assert "Player_ntrp_mid" in nicknames
    assert "Player_ntrp_low" not in nicknames
    assert "Player_ntrp_high" not in nicknames


@pytest.mark.asyncio
async def test_search_ideal_only(client: AsyncClient, session: AsyncSession):
    """ideal_only=true returns only ideal players."""
    token_a, _ = await _register(client, "ideal_searcher")
    _, id_b = await _register(client, "ideal_yes")
    _, _ = await _register(client, "ideal_no")

    user_b = await session.get(User, uuid.UUID(id_b))
    user_b.is_ideal_player = True
    await session.commit()

    resp = await client.get(
        "/api/v1/users/search",
        params={"ideal_only": "true"},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert data["total"] == 1
    assert data["users"][0]["nickname"] == "Player_ideal_yes"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_user_search.py -v`
Expected: FAIL — endpoint does not exist yet (404).

- [ ] **Step 3: Create service with basic filters**

Create `app/services/user_search.py`:

```python
import math
import uuid
from datetime import date

from sqlalchemy import Float, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block import Block
from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.court import Court
from app.models.follow import Follow
from app.models.matching import MatchPreference, MatchPreferenceCourt
from app.models.user import User
from app.services.booking import _ntrp_to_float


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


async def search_users(
    session: AsyncSession,
    *,
    caller_id: uuid.UUID,
    keyword: str | None = None,
    city: str | None = None,
    gender: str | None = None,
    min_ntrp: str | None = None,
    max_ntrp: str | None = None,
    court_id: uuid.UUID | None = None,
    radius_km: float = 10.0,
    ideal_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Search users with filters, sorting, and pagination."""

    # --- Subqueries ---

    # Block subquery: user IDs blocked in either direction
    blocked_ids = (
        select(Block.blocked_id)
        .where(Block.blocker_id == caller_id)
        .union(
            select(Block.blocker_id).where(Block.blocked_id == caller_id)
        )
    ).scalar_subquery()

    # Last active: most recent completed booking play_date
    last_active_sq = (
        select(func.max(Booking.play_date))
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == User.id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
        .correlate(User)
        .scalar_subquery()
    )

    # Is following: whether caller follows this user
    is_following_sq = (
        select(func.count())
        .select_from(Follow)
        .where(
            Follow.follower_id == caller_id,
            Follow.followed_id == User.id,
        )
        .correlate(User)
        .scalar_subquery()
    )

    # --- Base query ---

    query = (
        select(
            User,
            last_active_sq.label("last_active_at"),
            case((is_following_sq > 0, True), else_=False).label("is_following"),
        )
        .where(
            User.id != caller_id,
            User.is_active == True,
            User.is_suspended == False,
            User.id.not_in(blocked_ids),
        )
    )

    # --- Optional filters ---

    if keyword:
        query = query.where(User.nickname.ilike(f"%{keyword}%"))

    if city:
        query = query.where(User.city == city)

    if gender:
        query = query.where(User.gender == gender)

    if min_ntrp:
        min_val = _ntrp_to_float(min_ntrp)
        # Filter using cast: compare base ntrp (strip +/-)
        query = query.where(
            func.cast(func.regexp_replace(User.ntrp_level, r"[+-]$", ""), Float) >= min_val
        )

    if max_ntrp:
        max_val = _ntrp_to_float(max_ntrp)
        query = query.where(
            func.cast(func.regexp_replace(User.ntrp_level, r"[+-]$", ""), Float) <= max_val
        )

    if ideal_only:
        query = query.where(User.is_ideal_player == True)

    # --- Court proximity filter ---

    if court_id:
        ref_court = await session.get(Court, court_id)
        if ref_court and ref_court.latitude is not None and ref_court.longitude is not None:
            # Find all courts within radius
            all_courts_result = await session.execute(
                select(Court.id, Court.latitude, Court.longitude).where(
                    Court.latitude.is_not(None),
                    Court.longitude.is_not(None),
                )
            )
            nearby_court_ids = []
            for cid, lat, lng in all_courts_result.all():
                if _haversine_km(ref_court.latitude, ref_court.longitude, lat, lng) <= radius_km:
                    nearby_court_ids.append(cid)

            if nearby_court_ids:
                # Users with completed bookings at nearby courts
                booking_users = (
                    select(BookingParticipant.user_id)
                    .join(Booking, Booking.id == BookingParticipant.booking_id)
                    .where(
                        Booking.court_id.in_(nearby_court_ids),
                        Booking.status == BookingStatus.COMPLETED,
                        BookingParticipant.status == ParticipantStatus.ACCEPTED,
                    )
                )
                # Users with match preferences listing nearby courts
                pref_users = (
                    select(MatchPreference.user_id)
                    .join(MatchPreferenceCourt, MatchPreferenceCourt.preference_id == MatchPreference.id)
                    .where(MatchPreferenceCourt.court_id.in_(nearby_court_ids))
                )
                court_user_ids = booking_users.union(pref_users).scalar_subquery()
                query = query.where(User.id.in_(court_user_ids))
            else:
                # No courts in range — return empty
                query = query.where(False)

    # --- Count total before pagination ---

    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # --- Sort and paginate ---

    query = query.order_by(
        User.is_ideal_player.desc(),
        last_active_sq.desc().nulls_last(),
    )

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await session.execute(query)
    rows = result.all()

    users = []
    for row in rows:
        user = row[0]
        users.append({
            "id": user.id,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "gender": user.gender.value,
            "city": user.city,
            "ntrp_level": user.ntrp_level,
            "ntrp_label": user.ntrp_label,
            "bio": user.bio,
            "years_playing": user.years_playing,
            "is_ideal_player": user.is_ideal_player,
            "is_following": row[2],
            "last_active_at": row[1],
        })

    return {"users": users, "total": total, "page": page, "page_size": page_size}
```

- [ ] **Step 4: Commit**

```bash
git add app/services/user_search.py tests/test_user_search.py
git commit -m "feat(search): add user search service with basic filters and tests"
```

---

### Task 3: Router Integration

**Files:**

- Modify: `app/routers/users.py:1-12`

- [ ] **Step 1: Add search endpoint to users router**

Add the search endpoint in `app/routers/users.py`. It MUST be defined before `/{user_id}` routes to avoid path conflicts.

Add imports at the top of the file:

```python
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.schemas.stats import UserCalendar, UserStats
from app.schemas.user import UserProfileResponse, UserUpdateRequest
from app.schemas.user_search import UserSearchResponse
from app.services.block import is_blocked
from app.services.stats import get_user_calendar, get_user_stats
from app.services.user import update_user
from app.services.user_search import search_users

router = APIRouter()


@router.get("/search", response_model=UserSearchResponse)
async def search(
    session: DbSession,
    user: CurrentUser,
    keyword: str | None = Query(default=None, max_length=50),
    city: str | None = Query(default=None, max_length=50),
    gender: str | None = Query(default=None, pattern=r"^(male|female)$"),
    min_ntrp: str | None = Query(default=None, pattern=r"^\d\.\d[+-]?$"),
    max_ntrp: str | None = Query(default=None, pattern=r"^\d\.\d[+-]?$"),
    court_id: uuid.UUID | None = Query(default=None),
    radius_km: float = Query(default=10.0, ge=1.0, le=50.0),
    ideal_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
):
    result = await search_users(
        session,
        caller_id=user.id,
        keyword=keyword,
        city=city,
        gender=gender,
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        court_id=court_id,
        radius_km=radius_km,
        ideal_only=ideal_only,
        page=page,
        page_size=page_size,
    )
    return result


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(user: CurrentUser):
    return user
```

The rest of the file (`/me` PATCH, `/{user_id}/stats`, `/{user_id}/calendar`) remains unchanged.

- [ ] **Step 2: Run basic tests**

Run: `uv run pytest tests/test_user_search.py -v`
Expected: All 9 basic tests PASS.

- [ ] **Step 3: Commit**

```bash
git add app/routers/users.py app/schemas/user_search.py
git commit -m "feat(search): add GET /api/v1/users/search endpoint"
```

---

### Task 4: Court Proximity & Following Tests

**Files:**

- Modify: `tests/test_user_search.py`

- [ ] **Step 1: Add court proximity and following tests**

Append to `tests/test_user_search.py`:

```python
# --- Court proximity tests ---


@pytest.mark.asyncio
async def test_search_court_proximity_booking_history(client: AsyncClient, session: AsyncSession):
    """Court filter returns users who played at nearby courts."""
    court = await _seed_court(session, "Central Court", lat=22.28, lng=114.15)
    token_a, id_a = await _register(client, "court_searcher")
    _, id_b = await _register(client, "court_player")
    _, _ = await _register(client, "court_noplay")

    await _seed_completed_booking(session, court, [uuid.UUID(id_a), uuid.UUID(id_b)])

    resp = await client.get(
        "/api/v1/users/search",
        params={"court_id": str(court.id), "radius_km": "10"},
        headers=_auth(token_a),
    )
    data = resp.json()
    nicknames = [u["nickname"] for u in data["users"]]
    assert "Player_court_player" in nicknames
    assert "Player_court_noplay" not in nicknames


@pytest.mark.asyncio
async def test_search_court_proximity_respects_radius(client: AsyncClient, session: AsyncSession):
    """Users at courts beyond radius are excluded."""
    # Two courts ~100km apart
    court_near = await _seed_court(session, "Near Court", lat=22.28, lng=114.15)
    court_far = await _seed_court(session, "Far Court", lat=23.28, lng=114.15)

    token_a, id_a = await _register(client, "radius_searcher")
    _, id_near = await _register(client, "radius_near")
    _, id_far = await _register(client, "radius_far")

    await _seed_completed_booking(session, court_near, [uuid.UUID(id_a), uuid.UUID(id_near)])
    await _seed_completed_booking(session, court_far, [uuid.UUID(id_a), uuid.UUID(id_far)])

    resp = await client.get(
        "/api/v1/users/search",
        params={"court_id": str(court_near.id), "radius_km": "5"},
        headers=_auth(token_a),
    )
    data = resp.json()
    nicknames = [u["nickname"] for u in data["users"]]
    assert "Player_radius_near" in nicknames
    assert "Player_radius_far" not in nicknames


@pytest.mark.asyncio
async def test_search_court_includes_preferences(client: AsyncClient, session: AsyncSession):
    """Court filter includes users with matching match preferences."""
    from app.models.matching import MatchPreference, MatchPreferenceCourt

    court = await _seed_court(session, "Pref Court", lat=22.28, lng=114.15)
    token_a, _ = await _register(client, "pref_searcher")
    _, id_b = await _register(client, "pref_user")

    # Add match preference with this court
    pref = MatchPreference(
        user_id=uuid.UUID(id_b),
        min_ntrp="3.0",
        max_ntrp="4.0",
    )
    session.add(pref)
    await session.flush()
    session.add(MatchPreferenceCourt(preference_id=pref.id, court_id=court.id))
    await session.commit()

    resp = await client.get(
        "/api/v1/users/search",
        params={"court_id": str(court.id), "radius_km": "10"},
        headers=_auth(token_a),
    )
    data = resp.json()
    nicknames = [u["nickname"] for u in data["users"]]
    assert "Player_pref_user" in nicknames


# --- Sort order and following tests ---


@pytest.mark.asyncio
async def test_search_sort_ideal_first(client: AsyncClient, session: AsyncSession):
    """Ideal players appear before non-ideal players."""
    token_a, _ = await _register(client, "sort_searcher")
    _, id_normal = await _register(client, "sort_normal")
    _, id_ideal = await _register(client, "sort_ideal")

    user_ideal = await session.get(User, uuid.UUID(id_ideal))
    user_ideal.is_ideal_player = True
    await session.commit()

    resp = await client.get("/api/v1/users/search", headers=_auth(token_a))
    users = resp.json()["users"]
    ideal_idx = next(i for i, u in enumerate(users) if u["nickname"] == "Player_sort_ideal")
    normal_idx = next(i for i, u in enumerate(users) if u["nickname"] == "Player_sort_normal")
    assert ideal_idx < normal_idx


@pytest.mark.asyncio
async def test_search_is_following_field(client: AsyncClient, session: AsyncSession):
    """is_following reflects whether the caller follows each user."""
    token_a, id_a = await _register(client, "follow_searcher")
    _, id_followed = await _register(client, "follow_yes")
    _, id_not_followed = await _register(client, "follow_no")

    session.add(Follow(follower_id=uuid.UUID(id_a), followed_id=uuid.UUID(id_followed)))
    await session.commit()

    resp = await client.get("/api/v1/users/search", headers=_auth(token_a))
    users = {u["nickname"]: u for u in resp.json()["users"]}
    assert users["Player_follow_yes"]["is_following"] is True
    assert users["Player_follow_no"]["is_following"] is False


@pytest.mark.asyncio
async def test_search_pagination(client: AsyncClient, session: AsyncSession):
    """Pagination returns correct page and total."""
    token_a, _ = await _register(client, "page_searcher")
    for i in range(5):
        await _register(client, f"page_user_{i}")

    resp = await client.get(
        "/api/v1/users/search",
        params={"page": "1", "page_size": "2"},
        headers=_auth(token_a),
    )
    data = resp.json()
    assert len(data["users"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2

    resp2 = await client.get(
        "/api/v1/users/search",
        params={"page": "3", "page_size": "2"},
        headers=_auth(token_a),
    )
    data2 = resp2.json()
    assert len(data2["users"]) == 1


@pytest.mark.asyncio
async def test_search_no_filters_returns_all_eligible(client: AsyncClient, session: AsyncSession):
    """No filters returns all active, non-suspended, non-blocked users."""
    token_a, _ = await _register(client, "all_searcher")
    _, _ = await _register(client, "all_user_1")
    _, _ = await _register(client, "all_user_2")

    resp = await client.get("/api/v1/users/search", headers=_auth(token_a))
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_search_last_active_at_from_booking(client: AsyncClient, session: AsyncSession):
    """last_active_at reflects the most recent completed booking date."""
    court = await _seed_court(session, "Active Court")
    token_a, id_a = await _register(client, "active_searcher")
    _, id_b = await _register(client, "active_player")

    play_date = date(2026, 4, 10)
    await _seed_completed_booking(
        session, court, [uuid.UUID(id_a), uuid.UUID(id_b)], play_date=play_date,
    )

    resp = await client.get("/api/v1/users/search", headers=_auth(token_a))
    user_b = next(u for u in resp.json()["users"] if u["nickname"] == "Player_active_player")
    assert user_b["last_active_at"] == "2026-04-10"


@pytest.mark.asyncio
async def test_search_requires_auth(client: AsyncClient, session: AsyncSession):
    """Search endpoint requires authentication."""
    resp = await client.get("/api/v1/users/search")
    assert resp.status_code == 422 or resp.status_code == 401
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/test_user_search.py -v`
Expected: All 18 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_user_search.py
git commit -m "test(search): add court proximity, sorting, following, and pagination tests"
```

---

### Task 5: Full Test Suite Verification

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS. No regressions.

- [ ] **Step 2: Final commit (if any fixups needed)**

If any test needed fixing, commit the fix. Otherwise, this task is done.
