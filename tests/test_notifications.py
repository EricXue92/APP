import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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
async def test_empty_notifications(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_empty")

    resp = await client.get("/api/v1/notifications", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_unread_count_empty(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_count0")

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"unread_count": 0}


@pytest.mark.asyncio
async def test_mark_as_read(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_read1")
    token2, uid2 = await _register_and_get_token(client, "notif_read2")

    # Follow to create a notification
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    # uid1 should have 1 unread notification
    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 1

    # Get the notification
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    assert len(notifs) == 1
    assert notifs[0]["is_read"] is False
    notif_id = notifs[0]["id"]

    # Mark as read
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204

    # Unread count should be 0
    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_as_read_idempotent(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_idemp1")
    token2, uid2 = await _register_and_get_token(client, "notif_idemp2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notif_id = resp.json()[0]["id"]

    # Mark read twice — both should succeed
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_mark_as_read_wrong_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_wrong1")
    token2, uid2 = await _register_and_get_token(client, "notif_wrong2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notif_id = resp.json()[0]["id"]

    # uid2 tries to mark uid1's notification — should 404
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token2))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_as_read_nonexistent(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_ghost")
    fake_id = str(uuid.uuid4())

    resp = await client.patch(f"/api/v1/notifications/{fake_id}/read", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_as_read(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_all1")
    token2, uid2 = await _register_and_get_token(client, "notif_all2")
    token3, uid3 = await _register_and_get_token(client, "notif_all3")

    # Two follows → two notifications for uid1
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token3))

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 2

    # Mark all read
    resp = await client.patch("/api/v1/notifications/read-all", headers=_auth(token1))
    assert resp.status_code == 204

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_list_notifications_pagination(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_page1")

    # Create 3 followers → 3 notifications for uid1
    for i in range(3):
        tok, _ = await _register_and_get_token(client, f"notif_pager{i}")
        await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(tok))

    # Get all
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    assert len(resp.json()) == 3

    # Get first 2
    resp = await client.get("/api/v1/notifications?limit=2&offset=0", headers=_auth(token1))
    assert len(resp.json()) == 2

    # Get remaining
    resp = await client.get("/api/v1/notifications?limit=2&offset=2", headers=_auth(token1))
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_follow_creates_new_follower_notification(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "fnotif1")
    token2, uid2 = await _register_and_get_token(client, "fnotif2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    assert len(notifs) == 1
    assert notifs[0]["type"] == "new_follower"
    assert notifs[0]["actor_id"] == uid2
    assert notifs[0]["target_type"] == "follow"


@pytest.mark.asyncio
async def test_mutual_follow_creates_new_mutual_notification(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "mnotif1")
    token2, uid2 = await _register_and_get_token(client, "mnotif2")

    # A follows B → B gets new_follower
    await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))

    # B follows A → A gets new_follower, AND A gets new_mutual
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    # A should have: new_follower (from B) + new_mutual (B followed back)
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    types = [n["type"] for n in notifs]
    assert "new_follower" in types
    assert "new_mutual" in types

    # B should have: new_follower (from A)
    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    assert len(notifs) == 1
    assert notifs[0]["type"] == "new_follower"


# --- Booking notification helpers ---


async def _create_court(client: AsyncClient, token: str) -> str:
    """Create a court and return its id."""
    resp = await client.post(
        "/api/v1/courts",
        json={
            "name": "Test Court",
            "address": "123 Test St",
            "city": "Hong Kong",
            "court_type": "outdoor",
        },
        headers=_auth(token),
    )
    return resp.json()["id"]


async def _approve_court(session: AsyncSession, court_id: str):
    """Directly approve a court in the DB for testing."""
    from app.models.court import Court
    from sqlalchemy import select

    result = await session.execute(select(Court).where(Court.id == uuid.UUID(court_id)))
    court = result.scalar_one()
    court.is_approved = True
    await session.commit()


async def _create_booking(client: AsyncClient, token: str, court_id: str) -> str:
    """Create a booking and return its id."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": court_id,
            "match_type": "singles",
            "play_date": tomorrow,
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "2.0",
            "max_ntrp": "5.0",
            "gender_requirement": "any",
        },
        headers=_auth(token),
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_join_booking_notifies_creator(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c1")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j1")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    booking_notifs = [n for n in notifs if n["type"] == "booking_joined"]
    assert len(booking_notifs) == 1
    assert booking_notifs[0]["actor_id"] == uid2
    assert booking_notifs[0]["target_type"] == "booking"
    assert booking_notifs[0]["target_id"] == booking_id


@pytest.mark.asyncio
async def test_accept_participant_notifies_participant(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c2")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j2")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))

    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    accept_notifs = [n for n in notifs if n["type"] == "booking_accepted"]
    assert len(accept_notifs) == 1
    assert accept_notifs[0]["actor_id"] == uid1


@pytest.mark.asyncio
async def test_reject_participant_notifies_participant(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c3")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j3")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))

    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "rejected"},
        headers=_auth(token1),
    )

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    reject_notifs = [n for n in notifs if n["type"] == "booking_rejected"]
    assert len(reject_notifs) == 1


@pytest.mark.asyncio
async def test_cancel_booking_notifies_participants(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c4")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j4")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )

    await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=_auth(token1))

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    cancel_notifs = [n for n in notifs if n["type"] == "booking_cancelled"]
    assert len(cancel_notifs) == 1
    assert cancel_notifs[0]["actor_id"] == uid1


@pytest.mark.asyncio
async def test_confirm_booking_notifies_participants(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c5")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j5")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )

    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    confirm_notifs = [n for n in notifs if n["type"] == "booking_confirmed"]
    assert len(confirm_notifs) == 1


@pytest.mark.asyncio
async def test_complete_booking_notifies_participants(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "bnotif_c6")
    token2, uid2 = await _register_and_get_token(client, "bnotif_j6")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    # Patch play_date to past so complete is allowed
    from app.models.booking import Booking
    from sqlalchemy import select

    result = await session.execute(select(Booking).where(Booking.id == uuid.UUID(booking_id)))
    booking = result.scalar_one()
    booking.play_date = date.today() - timedelta(days=1)
    booking.start_time = time(10, 0)
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    notifs = resp.json()
    complete_notifs = [n for n in notifs if n["type"] == "booking_completed"]
    assert len(complete_notifs) == 1


# --- Review notification tests ---


@pytest.mark.asyncio
async def test_review_revealed_notifies_both_users(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "rnotif_c1")
    token2, uid2 = await _register_and_get_token(client, "rnotif_j1")

    court_id = await _create_court(client, token1)
    await _approve_court(session, court_id)
    booking_id = await _create_booking(client, token1, court_id)

    # Join, accept, confirm
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    # Set play_date to past and complete
    from app.models.booking import Booking
    from sqlalchemy import select

    result = await session.execute(select(Booking).where(Booking.id == uuid.UUID(booking_id)))
    booking = result.scalar_one()
    booking.play_date = date.today() - timedelta(days=1)
    booking.start_time = time(10, 0)
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    # User1 reviews User2 — no reveal yet
    await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 4,
        },
        headers=_auth(token1),
    )

    # Check no review_revealed notifications yet
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    reveal_notifs = [n for n in resp.json() if n["type"] == "review_revealed"]
    assert len(reveal_notifs) == 0

    # User2 reviews User1 — triggers reveal
    await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid1,
            "skill_rating": 3,
            "punctuality_rating": 4,
            "sportsmanship_rating": 5,
        },
        headers=_auth(token2),
    )

    # Both users should get review_revealed notification
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    reveal_notifs = [n for n in resp.json() if n["type"] == "review_revealed"]
    assert len(reveal_notifs) == 1
    assert reveal_notifs[0]["target_type"] == "review"

    resp = await client.get("/api/v1/notifications", headers=_auth(token2))
    reveal_notifs = [n for n in resp.json() if n["type"] == "review_revealed"]
    assert len(reveal_notifs) == 1
