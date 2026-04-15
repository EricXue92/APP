import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.court import Court, CourtType
from app.models.matching import MatchPreference, MatchTimeSlot, MatchPreferenceCourt, MatchTypePreference, GenderPreference
from app.models.user import AuthProvider, User
from app.services.matching import compute_match_score
from app.services.user import create_user_with_auth


async def _register_and_get_token(
    client: AsyncClient, username: str, gender: str = "male", ntrp: str = "3.5"
) -> tuple[str, str]:
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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Preference CRUD Tests ---


@pytest.mark.asyncio
async def test_create_preference(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "match1")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/matching/preferences",
        headers=_auth(token),
        json={
            "match_type": "singles",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_preference": "any",
            "time_slots": [
                {"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"},
                {"day_of_week": 6, "start_time": "14:00:00", "end_time": "17:00:00"},
            ],
            "court_ids": [str(court.id)],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["match_type"] == "singles"
    assert data["is_active"] is True
    assert len(data["time_slots"]) == 2
    assert data["court_ids"] == [str(court.id)]


@pytest.mark.asyncio
async def test_create_preference_duplicate(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match2")

    body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    resp1 = await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_preference_invalid_time(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match3")

    resp = await client.post(
        "/api/v1/matching/preferences",
        headers=_auth(token),
        json={
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "time_slots": [{"day_of_week": 5, "start_time": "09:15:00", "end_time": "12:00:00"}],
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_preference(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match4")

    body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)

    resp = await client.get("/api/v1/matching/preferences", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["min_ntrp"] == "3.0"


@pytest.mark.asyncio
async def test_get_preference_not_found(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match5")

    resp = await client.get("/api/v1/matching/preferences", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_preference(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match6")
    court = await _seed_court(session)

    body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)

    resp = await client.put(
        "/api/v1/matching/preferences",
        headers=_auth(token),
        json={
            "min_ntrp": "3.5",
            "max_ntrp": "4.5",
            "time_slots": [{"day_of_week": 6, "start_time": "14:00:00", "end_time": "17:00:00"}],
            "court_ids": [str(court.id)],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["min_ntrp"] == "3.5"
    assert len(data["time_slots"]) == 1
    assert data["time_slots"][0]["day_of_week"] == 6
    assert data["court_ids"] == [str(court.id)]


@pytest.mark.asyncio
async def test_toggle_preference(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "match7")

    body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token), json=body)

    resp = await client.patch("/api/v1/matching/preferences/toggle", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = await client.patch("/api/v1/matching/preferences/toggle", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


# --- Scoring Helper Functions ---


async def _create_user_direct(session: AsyncSession, username: str, **kwargs) -> User:
    defaults = {
        "nickname": f"Player_{username}",
        "gender": "male",
        "city": "Hong Kong",
        "ntrp_level": "3.5",
        "language": "en",
        "provider": AuthProvider.USERNAME,
        "provider_user_id": username,
        "password": "test1234",
    }
    defaults.update(kwargs)
    return await create_user_with_auth(session, **defaults)


async def _create_preference_direct(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    min_ntrp: str = "3.0",
    max_ntrp: str = "4.0",
    slots: list[tuple[int, str, str]] | None = None,
    court_ids: list[uuid.UUID] | None = None,
    gender_preference: str = "any",
    match_type: str = "singles",
) -> MatchPreference:
    pref = MatchPreference(
        user_id=user_id,
        match_type=MatchTypePreference(match_type),
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_preference=GenderPreference(gender_preference),
    )
    session.add(pref)
    await session.flush()

    if slots is None:
        slots = [(5, "09:00", "12:00")]
    for day, start, end in slots:
        ts = MatchTimeSlot(
            preference_id=pref.id,
            day_of_week=day,
            start_time=time.fromisoformat(start),
            end_time=time.fromisoformat(end),
        )
        session.add(ts)

    for cid in (court_ids or []):
        pc = MatchPreferenceCourt(preference_id=pref.id, court_id=cid)
        session.add(pc)

    await session.commit()
    # Eagerly reload with relationships to avoid lazy-load issues in async
    result = await session.execute(
        select(MatchPreference)
        .options(
            selectinload(MatchPreference.time_slots),
            selectinload(MatchPreference.preferred_courts),
        )
        .where(MatchPreference.id == pref.id)
    )
    return result.scalar_one()


# --- Scoring Tests ---


@pytest.mark.asyncio
async def test_score_perfect_match(client: AsyncClient, session: AsyncSession):
    """Two users with identical preferences should get a high score."""
    user_a = await _create_user_direct(session, "score_a")
    user_b = await _create_user_direct(session, "score_b")
    court = await _seed_court(session)

    pref_a = await _create_preference_direct(session, user_a.id, court_ids=[court.id])
    pref_b = await _create_preference_direct(session, user_b.id, court_ids=[court.id])

    score = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    assert score is not None
    assert score >= 80  # High score for perfect overlap


@pytest.mark.asyncio
async def test_score_ntrp_too_far(client: AsyncClient, session: AsyncSession):
    """NTRP gap > 1.5 should return None (filtered out)."""
    user_a = await _create_user_direct(session, "score_c", ntrp_level="2.0")
    user_b = await _create_user_direct(session, "score_d", ntrp_level="4.5")

    pref_a = await _create_preference_direct(session, user_a.id, min_ntrp="1.5", max_ntrp="2.5")
    pref_b = await _create_preference_direct(session, user_b.id, min_ntrp="4.0", max_ntrp="5.0")

    score = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    assert score is None


@pytest.mark.asyncio
async def test_score_no_time_overlap(client: AsyncClient, session: AsyncSession):
    """No overlapping time slots should return None."""
    user_a = await _create_user_direct(session, "score_e")
    user_b = await _create_user_direct(session, "score_f")

    pref_a = await _create_preference_direct(session, user_a.id, slots=[(0, "09:00", "12:00")])  # Monday
    pref_b = await _create_preference_direct(session, user_b.id, slots=[(5, "14:00", "17:00")])  # Saturday

    score = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    assert score is None


@pytest.mark.asyncio
async def test_score_gender_filter(client: AsyncClient, session: AsyncSession):
    """Gender mismatch with preference should return None."""
    user_a = await _create_user_direct(session, "score_g", gender="male")
    user_b = await _create_user_direct(session, "score_h", gender="male")

    pref_a = await _create_preference_direct(session, user_a.id, gender_preference="female_only")
    pref_b = await _create_preference_direct(session, user_b.id)

    score = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    assert score is None


@pytest.mark.asyncio
async def test_score_ideal_player_bonus(client: AsyncClient, session: AsyncSession):
    """Ideal player should score higher than non-ideal with same stats."""
    user_a = await _create_user_direct(session, "score_i")
    user_b = await _create_user_direct(session, "score_j")
    user_c = await _create_user_direct(session, "score_k")
    user_c.is_ideal_player = True
    await session.commit()

    court = await _seed_court(session)
    pref_a = await _create_preference_direct(session, user_a.id, court_ids=[court.id])
    pref_b = await _create_preference_direct(session, user_b.id, court_ids=[court.id])
    pref_c = await _create_preference_direct(session, user_c.id, court_ids=[court.id])

    score_b = await compute_match_score(session, user_a, pref_a, user_b, pref_b)
    score_c = await compute_match_score(session, user_a, pref_a, user_c, pref_c)
    assert score_c > score_b


# --- Candidate Search Tests ---


@pytest.mark.asyncio
async def test_search_candidates(client: AsyncClient, session: AsyncSession):
    """Should return compatible candidates sorted by score."""
    token_a, uid_a = await _register_and_get_token(client, "cand_a", ntrp="3.5")
    token_b, uid_b = await _register_and_get_token(client, "cand_b", ntrp="3.5")
    court = await _seed_court(session)

    # Both create preferences with overlapping time and same court
    pref_body = {
        "match_type": "singles",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
        "court_ids": [str(court.id)],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token_a), json=pref_body)
    await client.post("/api/v1/matching/preferences", headers=_auth(token_b), json=pref_body)

    resp = await client.get("/api/v1/matching/candidates", headers=_auth(token_a))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == uid_b
    assert data[0]["score"] > 0


@pytest.mark.asyncio
async def test_search_candidates_filters_blocked(client: AsyncClient, session: AsyncSession):
    """Blocked users should not appear in candidates."""
    token_a, uid_a = await _register_and_get_token(client, "cand_c", ntrp="3.5")
    token_b, uid_b = await _register_and_get_token(client, "cand_d", ntrp="3.5")
    court = await _seed_court(session)

    pref_body = {
        "match_type": "singles",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
        "court_ids": [str(court.id)],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token_a), json=pref_body)
    await client.post("/api/v1/matching/preferences", headers=_auth(token_b), json=pref_body)

    # Block user B
    await client.post("/api/v1/blocks", headers=_auth(token_a), json={"blocked_id": uid_b})

    resp = await client.get("/api/v1/matching/candidates", headers=_auth(token_a))
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_search_candidates_no_preference(client: AsyncClient, session: AsyncSession):
    """Should return 404 if user has no preference."""
    token, _ = await _register_and_get_token(client, "cand_e")

    resp = await client.get("/api/v1/matching/candidates", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_candidates_inactive(client: AsyncClient, session: AsyncSession):
    """Should return 400 if preference is inactive."""
    token, _ = await _register_and_get_token(client, "cand_f")

    pref_body = {
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token), json=pref_body)
    await client.patch("/api/v1/matching/preferences/toggle", headers=_auth(token))

    resp = await client.get("/api/v1/matching/candidates", headers=_auth(token))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_booking_recommendations(client: AsyncClient, session: AsyncSession):
    """Should return open bookings matching user's preferences."""
    token_a, uid_a = await _register_and_get_token(client, "brec_a", ntrp="3.5")
    token_b, uid_b = await _register_and_get_token(client, "brec_b", ntrp="3.5")
    court = await _seed_court(session)

    # User A creates a preference
    pref_body = {
        "match_type": "singles",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "time_slots": [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "12:00:00"}],
        "court_ids": [str(court.id)],
    }
    await client.post("/api/v1/matching/preferences", headers=_auth(token_a), json=pref_body)

    # User B creates a booking on a Saturday (day_of_week=5)
    today = date.today()
    days_until_sat = (5 - today.weekday()) % 7
    if days_until_sat == 0:
        days_until_sat = 7
    next_sat = today + timedelta(days=days_until_sat)

    await client.post(
        "/api/v1/bookings",
        headers=_auth(token_b),
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": next_sat.isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )

    resp = await client.get("/api/v1/matching/bookings", headers=_auth(token_a))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["creator_nickname"] == "Player_brec_b"
    assert data[0]["score"] > 0
