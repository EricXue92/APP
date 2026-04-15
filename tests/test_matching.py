import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.user import AuthProvider, User


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
