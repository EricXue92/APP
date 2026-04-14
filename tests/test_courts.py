import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType


async def _register_and_get_token(client: AsyncClient, username: str = "courtuser") -> str:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "CourtTest",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    return resp.json()["access_token"]


async def _seed_approved_court(session: AsyncSession, name: str = "Victoria Park Tennis", city: str = "Hong Kong") -> Court:
    court = Court(
        name=name,
        address="1 Hing Fat St, Causeway Bay",
        city=city,
        latitude=22.282,
        longitude=114.188,
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


@pytest.mark.asyncio
async def test_list_courts_empty(client: AsyncClient):
    resp = await client.get("/api/v1/courts")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_courts_with_seeded(client: AsyncClient, session: AsyncSession):
    await _seed_approved_court(session)
    resp = await client.get("/api/v1/courts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Victoria Park Tennis"
    assert data[0]["is_approved"] is True


@pytest.mark.asyncio
async def test_list_courts_filter_by_city(client: AsyncClient, session: AsyncSession):
    await _seed_approved_court(session, name="HK Court", city="Hong Kong")
    await _seed_approved_court(session, name="BJ Court", city="Beijing")
    resp = await client.get("/api/v1/courts", params={"city": "Hong Kong"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "HK Court"


@pytest.mark.asyncio
async def test_list_courts_excludes_unapproved(client: AsyncClient, session: AsyncSession):
    await _seed_approved_court(session)
    unapproved = Court(
        name="User Court",
        address="Some address",
        city="Hong Kong",
        court_type=CourtType.INDOOR,
        is_approved=False,
    )
    session.add(unapproved)
    await session.commit()

    resp = await client.get("/api/v1/courts")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Victoria Park Tennis"


@pytest.mark.asyncio
async def test_get_court_by_id(client: AsyncClient, session: AsyncSession):
    court = await _seed_approved_court(session)
    resp = await client.get(f"/api/v1/courts/{court.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Victoria Park Tennis"


@pytest.mark.asyncio
async def test_get_court_unapproved_returns_404(client: AsyncClient, session: AsyncSession):
    court = Court(
        name="Unapproved",
        address="Addr",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=False,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)

    resp = await client.get(f"/api/v1/courts/{court.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_court_by_user(client: AsyncClient):
    token = await _register_and_get_token(client)
    resp = await client.post(
        "/api/v1/courts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "My Local Court",
            "address": "123 Tennis Lane",
            "city": "Hong Kong",
            "court_type": "outdoor",
            "surface_type": "hard",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Local Court"
    assert data["is_approved"] is False


@pytest.mark.asyncio
async def test_submit_court_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/courts",
        json={
            "name": "No Auth Court",
            "address": "456 Fake St",
            "city": "Hong Kong",
            "court_type": "indoor",
        },
    )
    assert resp.status_code == 422
