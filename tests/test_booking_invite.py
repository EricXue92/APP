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


# --- Accept invite tests ---


@pytest.mark.asyncio
async def test_accept_invite(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_acc_a")
    token_b, user_b = await _register_and_get_token(client, "inv_acc_b")
    court = await _seed_court(session)

    # Create invite
    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # Accept
    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/accept",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["booking_id"] is not None

    # Verify booking was created and confirmed
    booking_resp = await client.get(
        f"/api/v1/bookings/{data['booking_id']}",
        headers=_auth(token_a),
    )
    assert booking_resp.status_code == 200
    assert booking_resp.json()["status"] == "confirmed"
    assert len(booking_resp.json()["participants"]) == 2


@pytest.mark.asyncio
async def test_accept_invite_not_invitee(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_notinv_a")
    _, user_b = await _register_and_get_token(client, "inv_notinv_b")
    token_c, _ = await _register_and_get_token(client, "inv_notinv_c")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # C tries to accept
    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/accept",
        headers=_auth(token_c),
    )
    assert resp.status_code == 403


# --- Reject invite tests ---


@pytest.mark.asyncio
async def test_reject_invite(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_rej_a")
    token_b, user_b = await _register_and_get_token(client, "inv_rej_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/reject",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_accept_already_rejected(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_rejed_a")
    token_b, user_b = await _register_and_get_token(client, "inv_rejed_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # Reject first
    await client.post(f"/api/v1/bookings/invites/{invite_id}/reject", headers=_auth(token_b))

    # Try to accept
    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/accept",
        headers=_auth(token_b),
    )
    assert resp.status_code == 400


# --- List & detail tests ---


@pytest.mark.asyncio
async def test_list_sent_invites(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_ls_a")
    _, user_b = await _register_and_get_token(client, "inv_ls_b")
    court = await _seed_court(session)

    await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )

    resp = await client.get("/api/v1/bookings/invites/sent", headers=_auth(token_a))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_list_received_invites(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_lr_a")
    token_b, user_b = await _register_and_get_token(client, "inv_lr_b")
    court = await _seed_court(session)

    await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )

    resp = await client.get("/api/v1/bookings/invites/received", headers=_auth(token_b))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_invite_detail(client: AsyncClient, session: AsyncSession):
    token_a, user_a = await _register_and_get_token(client, "inv_det_a")
    token_b, user_b = await _register_and_get_token(client, "inv_det_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # Both parties can see detail
    resp_a = await client.get(f"/api/v1/bookings/invites/{invite_id}", headers=_auth(token_a))
    assert resp_a.status_code == 200

    resp_b = await client.get(f"/api/v1/bookings/invites/{invite_id}", headers=_auth(token_b))
    assert resp_b.status_code == 200


@pytest.mark.asyncio
async def test_get_invite_detail_forbidden(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_forb_a")
    _, user_b = await _register_and_get_token(client, "inv_forb_b")
    token_c, _ = await _register_and_get_token(client, "inv_forb_c")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    # C cannot see
    resp_c = await client.get(f"/api/v1/bookings/invites/{invite_id}", headers=_auth(token_c))
    assert resp_c.status_code == 403


# --- Edge Case: Accept expired invite ---

@pytest.mark.asyncio
async def test_accept_expired_invite(client: AsyncClient, session: AsyncSession):
    """Accepting an invite whose play_date has passed should fail."""
    token_a, _ = await _register_and_get_token(client, "inv_exp_a")
    token_b, user_b = await _register_and_get_token(client, "inv_exp_b")
    court = await _seed_court(session)

    # Create invite with past play_date by patching after creation
    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 201
    invite_id = resp.json()["id"]

    # Backdate the play_date to yesterday
    from sqlalchemy import update
    from app.models.booking_invite import BookingInvite
    await session.execute(
        update(BookingInvite)
        .where(BookingInvite.id == uuid.UUID(invite_id))
        .values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    # Try to accept — should fail because invite is now expired
    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/accept",
        headers=_auth(token_b),
    )
    assert resp.status_code == 400


# --- Edge Case: New invite after rejected one ---

@pytest.mark.asyncio
async def test_new_invite_after_rejection(client: AsyncClient, session: AsyncSession):
    """After rejecting an invite, the inviter can send a new one."""
    token_a, _ = await _register_and_get_token(client, "inv_rerej_a")
    token_b, user_b = await _register_and_get_token(client, "inv_rerej_b")
    court = await _seed_court(session)

    # First invite
    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 201
    invite_id = resp.json()["id"]

    # Reject it
    resp = await client.post(f"/api/v1/bookings/invites/{invite_id}/reject", headers=_auth(token_b))
    assert resp.status_code == 200

    # Send a new invite — should succeed (previous one is not pending anymore)
    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 201


# --- Edge Case: Accept creates booking and chat room ---

@pytest.mark.asyncio
async def test_accept_invite_creates_booking_and_room(client: AsyncClient, session: AsyncSession):
    """Accepting an invite should create a confirmed booking with a chat room."""
    from sqlalchemy import select
    from app.models.booking import Booking, BookingStatus
    from app.models.chat import ChatRoom

    token_a, user_a = await _register_and_get_token(client, "inv_accbk_a")
    token_b, user_b = await _register_and_get_token(client, "inv_accbk_b")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    invite_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/invites/{invite_id}/accept", headers=_auth(token_b))
    assert resp.status_code == 200
    invite_data = resp.json()
    assert invite_data["status"] == "accepted"
    booking_id = invite_data.get("booking_id")
    assert booking_id is not None

    # Verify booking exists and is confirmed
    result = await session.execute(
        select(Booking).where(Booking.id == uuid.UUID(booking_id))
    )
    booking = result.scalar_one()
    assert booking.status == BookingStatus.CONFIRMED

    # Verify chat room exists
    result = await session.execute(
        select(ChatRoom).where(ChatRoom.booking_id == uuid.UUID(booking_id))
    )
    room = result.scalar_one_or_none()
    assert room is not None


# --- Edge Case: Invite suspended invitee ---

@pytest.mark.asyncio
async def test_invite_suspended_user(client: AsyncClient, session: AsyncSession):
    """Inviting a suspended user should not crash; invite is created but invitee can't act on it."""
    from sqlalchemy import update as sa_update
    from app.models.user import User

    token_a, _ = await _register_and_get_token(client, "inv_susp_a")
    token_b, user_b = await _register_and_get_token(client, "inv_susp_b")
    court = await _seed_court(session)

    # Suspend user_b
    await session.execute(
        sa_update(User).where(User.id == uuid.UUID(user_b)).values(is_suspended=True)
    )
    await session.commit()

    # Creating the invite should still succeed (service doesn't check suspension)
    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token_a),
        json=_invite_body(user_b, str(court.id)),
    )
    assert resp.status_code == 201

    invite_id = resp.json()["id"]

    # Suspended user cannot accept (403 from auth middleware)
    resp = await client.post(
        f"/api/v1/bookings/invites/{invite_id}/accept",
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


# --- Edge Case: Get non-existent invite ---

@pytest.mark.asyncio
async def test_get_nonexistent_invite(client: AsyncClient, session: AsyncSession):
    token_a, _ = await _register_and_get_token(client, "inv_noexist")
    fake_id = str(uuid.uuid4())

    resp = await client.get(f"/api/v1/bookings/invites/{fake_id}", headers=_auth(token_a))
    assert resp.status_code == 404
