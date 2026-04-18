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
