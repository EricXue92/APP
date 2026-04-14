import uuid
from datetime import date, time, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.user import User


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


async def _create_booking(client: AsyncClient, token: str, court_id: str) -> dict:
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "court_id": court_id,
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
            "description": "Friendly match",
        },
    )
    return resp


# --- Create Booking Tests ---

@pytest.mark.asyncio
async def test_create_booking(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "creator1")
    court = await _seed_court(session)

    resp = await _create_booking(client, token, str(court.id))
    assert resp.status_code == 201
    data = resp.json()
    assert data["match_type"] == "singles"
    assert data["status"] == "open"
    assert data["max_participants"] == 2
    assert len(data["participants"]) == 1
    assert data["participants"][0]["status"] == "accepted"
    assert data["court_name"] == "Test Court"


@pytest.mark.asyncio
async def test_create_booking_credit_too_low(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "lowcredit")
    court = await _seed_court(session)

    # Set credit score below 60
    from sqlalchemy import update
    await session.execute(update(User).where(User.id == uuid.UUID(user_id)).values(credit_score=50))
    await session.commit()

    resp = await _create_booking(client, token, str(court.id))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_booking_unapproved_court(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "badcourt")
    court = Court(name="Unapproved", address="Addr", city="HK", court_type=CourtType.INDOOR, is_approved=False)
    session.add(court)
    await session.commit()
    await session.refresh(court)

    resp = await _create_booking(client, token, str(court.id))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_booking_doubles_max_4(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "doubles1")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "court_id": str(court.id),
            "match_type": "doubles",
            "play_date": _future_date(),
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["max_participants"] == 4


# --- Join Booking Tests ---

@pytest.mark.asyncio
async def test_join_booking(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host2")
    token2, _ = await _register_and_get_token(client, "joiner2")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/join",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["participants"]) == 2


@pytest.mark.asyncio
async def test_join_booking_duplicate(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host3")
    token2, _ = await _register_and_get_token(client, "joiner3")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_join_booking_ntrp_out_of_range(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host4", ntrp="3.5")
    token2, _ = await _register_and_get_token(client, "joiner4", ntrp="5.0")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_join_booking_gender_mismatch(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host5", gender="male")
    token2, _ = await _register_and_get_token(client, "joiner5", gender="female")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "male_only",
        },
    )
    booking_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_join_booking_full(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host6")
    token2, _ = await _register_and_get_token(client, "joiner6a")
    token3, _ = await _register_and_get_token(client, "joiner6b")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # joiner6a joins
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})

    # Creator accepts joiner6a
    joiner6a_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner6a_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # joiner6b tries to join — should fail (full)
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token3}"})
    assert resp.status_code == 409


# --- Confirm Booking Tests ---

@pytest.mark.asyncio
async def test_confirm_booking(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host7")
    token2, _ = await _register_and_get_token(client, "joiner7")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # Join and accept
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    joiner_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Confirm
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_confirm_not_enough_participants(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host8")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_confirm_not_creator(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host9")
    token2, _ = await _register_and_get_token(client, "joiner9")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 403


# --- Cancel Booking Tests ---

@pytest.mark.asyncio
async def test_cancel_booking_by_creator(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "host10")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_first_time_no_deduction(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "host11")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {token1}"})

    # Check credit score unchanged (first cancel = warning)
    profile = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token1}"})
    assert profile.json()["credit_score"] == 80


# --- Complete Booking Tests ---

@pytest.mark.asyncio
async def test_complete_booking_awards_credit(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host12")
    token2, _ = await _register_and_get_token(client, "joiner12")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # Join and accept
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    joiner_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Confirm
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})

    # Manually set play_date to past so complete works
    from app.models.booking import Booking
    from sqlalchemy import update
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    # Complete
    resp = await client.post(f"/api/v1/bookings/{booking_id}/complete", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # Check both users got +5 credit
    profile1 = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token1}"})
    assert profile1.json()["credit_score"] == 85

    profile2 = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token2}"})
    assert profile2.json()["credit_score"] == 85


@pytest.mark.asyncio
async def test_complete_before_play_time_fails(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host13")
    token2, _ = await _register_and_get_token(client, "joiner13")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # Join, accept, confirm
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    joiner_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})

    # Try to complete — play date is in the future
    resp = await client.post(f"/api/v1/bookings/{booking_id}/complete", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 400


# --- List Bookings Tests ---

@pytest.mark.asyncio
async def test_list_bookings(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "lister1")
    court = await _seed_court(session)

    await _create_booking(client, token, str(court.id))

    resp = await client.get("/api/v1/bookings")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_list_my_bookings(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "mylist1")
    token2, _ = await _register_and_get_token(client, "mylist2")
    court = await _seed_court(session)

    await _create_booking(client, token1, str(court.id))
    await _create_booking(client, token2, str(court.id))

    resp = await client.get("/api/v1/bookings/my", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --- Participant Management Tests ---

@pytest.mark.asyncio
async def test_accept_participant(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host14")
    token2, _ = await _register_and_get_token(client, "joiner14")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})

    detail = await client.get(f"/api/v1/bookings/{booking_id}")
    joiner_id = detail.json()["participants"][1]["user_id"]
    assert detail.json()["participants"][1]["status"] == "pending"

    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )
    assert resp.status_code == 200
    accepted = [p for p in resp.json()["participants"] if p["user_id"] == joiner_id]
    assert accepted[0]["status"] == "accepted"


@pytest.mark.asyncio
async def test_reject_participant(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "host15")
    token2, _ = await _register_and_get_token(client, "joiner15")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})

    detail = await client.get(f"/api/v1/bookings/{booking_id}")
    joiner_id = detail.json()["participants"][1]["user_id"]

    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "rejected"},
    )
    assert resp.status_code == 200
    rejected = [p for p in resp.json()["participants"] if p["user_id"] == joiner_id]
    assert rejected[0]["status"] == "rejected"


# --- Additional Tests ---

@pytest.mark.asyncio
async def test_create_booking_past_date_fails(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "pastdate1")
    court = await _seed_court(session)

    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() - timedelta(days=1)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_participant_cancel_own_participation(client: AsyncClient, session: AsyncSession):
    """Non-creator participant cancels their own participation — booking stays open."""
    token1, _ = await _register_and_get_token(client, "host16")
    token2, _ = await _register_and_get_token(client, "joiner16")
    court = await _seed_court(session)

    create_resp = await _create_booking(client, token1, str(court.id))
    booking_id = create_resp.json()["id"]

    # Join and accept
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    joiner_id = (await client.get(f"/api/v1/bookings/{booking_id}")).json()["participants"][1]["user_id"]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Participant cancels
    resp = await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"  # booking stays open
    # Participant's status should be cancelled
    participants = resp.json()["participants"]
    joiner_p = [p for p in participants if p["user_id"] == joiner_id]
    assert joiner_p[0]["status"] == "cancelled"
