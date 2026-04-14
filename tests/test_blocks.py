import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType


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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_block_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "blocker1")
    token2, uid2 = await _register_and_get_token(client, "blocked1")

    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201
    data = resp.json()
    assert data["blocker_id"] == uid1
    assert data["blocked_id"] == uid2


@pytest.mark.asyncio
async def test_block_self_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "selfblocker")

    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid1}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_block_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "dupblocker")
    token2, uid2 = await _register_and_get_token(client, "dupblocked")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unblock_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "unblocker")
    token2, uid2 = await _register_and_get_token(client, "unblocked")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    resp = await client.delete(f"/api/v1/blocks/{uid2}", headers=_auth(token1))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_unblock_nonexistent(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "unblocker2")
    fake_id = str(uuid.uuid4())

    resp = await client.delete(f"/api/v1/blocks/{fake_id}", headers=_auth(token1))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_blocks(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "lister1")
    token2, uid2 = await _register_and_get_token(client, "listed1")
    token3, uid3 = await _register_and_get_token(client, "listed2")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    await client.post("/api/v1/blocks", json={"blocked_id": uid3}, headers=_auth(token1))

    resp = await client.get("/api/v1/blocks", headers=_auth(token1))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


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


@pytest.mark.asyncio
async def test_blocked_review_submit_rejected(client: AsyncClient, session: AsyncSession):
    """New review between blocked pair should be rejected."""
    from app.models.booking import Booking
    from sqlalchemy import update as sa_update

    token1, uid1 = await _register_and_get_token(client, "blockrev1")
    token2, uid2 = await _register_and_get_token(client, "blockrev2")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    await session.execute(
        sa_update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(
            play_date=date.today() - timedelta(days=1),
        )
    )
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    # Block user2
    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    # Try to submit a review — should be rejected
    resp = await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid2,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
        headers=_auth(token1),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_blocked_user_cannot_join_booking(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "creator1")
    token2, uid2 = await _register_and_get_token(client, "joiner1")
    court = await _seed_court(session)

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_blocked_user_bookings_hidden_from_listing(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "listcreator")
    token2, uid2 = await _register_and_get_token(client, "listviewer")
    court = await _seed_court(session)

    await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )

    await client.post("/api/v1/blocks", json={"blocked_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/bookings", headers=_auth(token2))
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_reviews_hidden_on_block(client: AsyncClient, session: AsyncSession):
    """When user A blocks user B, existing reviews between them should be hidden."""
    from app.models.booking import Booking
    from app.models.review import Review
    from sqlalchemy import update

    token1, uid1 = await _register_and_get_token(client, "revblock1")
    token2, uid2 = await _register_and_get_token(client, "revblock2")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    await session.execute(
        update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(
            play_date=date.today() - timedelta(days=1),
        )
    )
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    await client.post(
        "/api/v1/reviews",
        json={"booking_id": booking_id, "reviewee_id": uid2, "skill_rating": 4, "punctuality_rating": 4, "sportsmanship_rating": 4},
        headers=_auth(token1),
    )
    await client.post(
        "/api/v1/reviews",
        json={"booking_id": booking_id, "reviewee_id": uid1, "skill_rating": 4, "punctuality_rating": 4, "sportsmanship_rating": 4},
        headers=_auth(token2),
    )

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    from sqlalchemy import select as sa_select
    result = await session.execute(
        sa_select(Review).where(Review.booking_id == uuid.UUID(booking_id))
    )
    reviews = list(result.scalars().all())
    assert all(r.is_hidden for r in reviews)


@pytest.mark.asyncio
async def test_suspended_user_rejected(client: AsyncClient, session: AsyncSession):
    """Suspended user's token should be rejected on all protected endpoints."""
    from app.models.user import User
    from sqlalchemy import update

    token1, uid1 = await _register_and_get_token(client, "suspended1")

    # Suspend the user directly in DB
    await session.execute(
        update(User).where(User.id == uuid.UUID(uid1)).values(is_suspended=True)
    )
    await session.commit()

    # Try to access a protected endpoint
    resp = await client.get("/api/v1/blocks", headers=_auth(token1))
    assert resp.status_code == 403
    assert "suspended" in resp.json()["detail"].lower()
