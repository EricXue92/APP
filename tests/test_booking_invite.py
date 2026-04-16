import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.notification import NotificationType
from app.models.booking_invite import InviteStatus


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


def _invite_body(invitee_id: str, court_id: str, **overrides) -> dict:
    body = {
        "invitee_id": invitee_id,
        "court_id": court_id,
        "match_type": "singles",
        "play_date": str(date.today() + timedelta(days=3)),
        "start_time": "14:00:00",
        "end_time": "16:00:00",
    }
    body.update(overrides)
    return body


# --- Create invite tests ---


@pytest.mark.asyncio
async def test_create_invite_success(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_a")
    _, user_b = await _register_and_get_token(client, "inv_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["inviter_id"] == user_a
    assert data["invitee_id"] == user_b
    assert data["status"] == "pending"
    assert data["booking_id"] is None


@pytest.mark.asyncio
async def test_create_invite_self(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_self")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_a, str(court.id)),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_invite_duplicate_pending(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_dup_a")
    _, user_b = await _register_and_get_token(client, "inv_dup_b")
    court = await _seed_court(session)

    body = _invite_body(user_b, str(court.id))
    resp1 = await client.post("/api/v1/bookings/invites", headers=_auth(token_a), json=body)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/bookings/invites", headers=_auth(token_a), json=body)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_invite_past_date(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_past_a")
    _, user_b = await _register_and_get_token(client, "inv_past_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id), play_date=str(date.today() - timedelta(days=1))),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_invite_blocked(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_blk_a")
    token_b, user_b = await _register_and_get_token(client, "inv_blk_b")
    court = await _seed_court(session)

    # B blocks A
    await client.post("/api/v1/blocks", headers=_auth(token_b), json={"blocked_id": user_a})

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_invite_low_credit(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_lowcr_a")
    _, user_b = await _register_and_get_token(client, "inv_lowcr_b")
    court = await _seed_court(session)

    # Set credit below 60
    from app.models.user import User
    from sqlalchemy import select
    result = await session.execute(select(User).where(User.id == uuid.UUID(user_a)))
    u = result.scalar_one()
    u.credit_score = 50
    await session.commit()

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 403
