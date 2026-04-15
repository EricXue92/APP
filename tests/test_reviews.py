import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.court import Court, CourtType
from app.models.review import Review
from app.models.user import User
from app.services.review import get_booking_reviews_for_user, get_review_averages


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


async def _create_completed_booking(
    client: AsyncClient,
    session: AsyncSession,
    token1: str,
    token2: str,
    court_id: str,
) -> str:
    """Create a booking, join token2, accept, confirm, backdate, complete. Returns booking_id."""
    # Create booking
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": court_id,
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
            "description": "Review test match",
        },
    )
    assert resp.status_code == 201, f"Create booking failed: {resp.json()}"
    booking_id = resp.json()["id"]

    # Token2 joins
    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/join",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200, f"Join failed: {resp.json()}"

    # Get joiner's user_id from participants
    detail = await client.get(f"/api/v1/bookings/{booking_id}")
    participants = detail.json()["participants"]
    joiner_id = [p["user_id"] for p in participants if p["status"] == "pending"][0]

    # Accept
    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )
    assert resp.status_code == 200, f"Accept failed: {resp.json()}"

    # Confirm
    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/confirm",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200, f"Confirm failed: {resp.json()}"

    # Backdate play_date to past so complete works
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    # Complete
    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/complete",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200, f"Complete failed: {resp.json()}"
    assert resp.json()["status"] == "completed"

    return booking_id


# --- Submit Review Tests ---


@pytest.mark.asyncio
async def test_submit_review_success(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_s1")
    token2, user_id2 = await _register_and_get_token(client, "rev_s2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
            "comment": "Great match!",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reviewer_id"] == user_id1
    assert data["reviewee_id"] == user_id2
    assert data["is_revealed"] is False
    assert data["skill_rating"] == 4


@pytest.mark.asyncio
async def test_submit_review_booking_not_completed(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_nc1")
    token2, user_id2 = await _register_and_get_token(client, "rev_nc2")
    court = await _seed_court(session)

    # Create booking but don't complete it
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
            "gender_requirement": "any",
        },
    )
    booking_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_submit_review_not_participant(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_np1")
    token2, user_id2 = await _register_and_get_token(client, "rev_np2")
    token3, user_id3 = await _register_and_get_token(client, "rev_np3")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Outsider (token3) tries to review
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token3}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_review_self(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_self1")
    token2, user_id2 = await _register_and_get_token(client, "rev_self2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Try self-review
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id1,
            "skill_rating": 5,
            "punctuality_rating": 5,
            "sportsmanship_rating": 5,
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_submit_review_duplicate(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_dup1")
    token2, user_id2 = await _register_and_get_token(client, "rev_dup2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    review_body = {
        "booking_id": booking_id,
        "reviewee_id": user_id2,
        "skill_rating": 4,
        "punctuality_rating": 5,
        "sportsmanship_rating": 3,
    }

    # First review
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json=review_body,
    )
    assert resp.status_code == 201

    # Duplicate
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json=review_body,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_submit_review_invalid_rating(client: AsyncClient, session: AsyncSession):
    """Ratings outside 1-5 are rejected by Pydantic validation (422)."""
    token1, user_id1 = await _register_and_get_token(client, "rev_inv1")
    token2, user_id2 = await _register_and_get_token(client, "rev_inv2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 6,
            "punctuality_rating": 0,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_review_window_expired(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_exp1")
    token2, user_id2 = await _register_and_get_token(client, "rev_exp2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Backdate updated_at to more than 24h ago
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(updated_at=datetime.now(timezone.utc) - timedelta(hours=25))
    )
    await session.commit()

    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code == 400


# --- Blind Reveal Tests ---


@pytest.mark.asyncio
async def test_blind_reveal_single_side_not_visible(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_br1")
    token2, user_id2 = await _register_and_get_token(client, "rev_br2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Only user1 reviews user2
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code == 201

    # User2's profile should show 0 reviews (not revealed)
    resp = await client.get(f"/api/v1/reviews/users/{user_id2}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 0
    assert len(data["reviews"]) == 0


@pytest.mark.asyncio
async def test_blind_reveal_both_sides_visible(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_bv1")
    token2, user_id2 = await _register_and_get_token(client, "rev_bv2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # User1 reviews user2
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code == 201

    # User2 reviews user1
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id1,
            "skill_rating": 2,
            "punctuality_rating": 3,
            "sportsmanship_rating": 4,
        },
    )
    assert resp.status_code == 201
    # Second review should trigger reveal
    assert resp.json()["is_revealed"] is True

    # User2's profile: 1 review with correct ratings
    resp = await client.get(f"/api/v1/reviews/users/{user_id2}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 1
    assert len(data["reviews"]) == 1
    assert data["average_skill"] == 4.0
    assert data["average_punctuality"] == 5.0
    assert data["average_sportsmanship"] == 3.0

    # User1's profile: 1 review with correct ratings
    resp = await client.get(f"/api/v1/reviews/users/{user_id1}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 1
    assert len(data["reviews"]) == 1
    assert data["average_skill"] == 2.0
    assert data["average_punctuality"] == 3.0
    assert data["average_sportsmanship"] == 4.0


@pytest.mark.asyncio
async def test_reviewer_sees_own_review(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_own1")
    token2, user_id2 = await _register_and_get_token(client, "rev_own2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # User1 reviews user2
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code == 201

    # Reviewer (user1) sees own review in booking reviews
    resp = await client.get(
        f"/api/v1/reviews/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["reviewer_id"] == user_id1
    assert data[0]["is_revealed"] is False

    # Reviewee (user2) sees nothing — review not revealed yet
    resp = await client.get(
        f"/api/v1/reviews/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


# --- Pending Reviews Tests ---


@pytest.mark.asyncio
async def test_pending_reviews_shows_unreviewed(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_pend1")
    token2, user_id2 = await _register_and_get_token(client, "rev_pend2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    resp = await client.get(
        "/api/v1/reviews/pending",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["booking_id"] == booking_id
    assert data[0]["court_name"] == "Test Court"
    assert len(data[0]["reviewees"]) == 1
    assert data[0]["reviewees"][0]["user_id"] == user_id2


@pytest.mark.asyncio
async def test_pending_reviews_excludes_already_reviewed(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_pexcl1")
    token2, user_id2 = await _register_and_get_token(client, "rev_pexcl2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Submit review
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code == 201

    # No more pending
    resp = await client.get(
        "/api/v1/reviews/pending",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_pending_reviews_excludes_expired_window(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_pexp1")
    token2, user_id2 = await _register_and_get_token(client, "rev_pexp2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Backdate updated_at past the 24h window
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(updated_at=datetime.now(timezone.utc) - timedelta(hours=25))
    )
    await session.commit()

    resp = await client.get(
        "/api/v1/reviews/pending",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


# --- User Reviews / Averages Tests ---


@pytest.mark.asyncio
async def test_user_reviews_empty(client: AsyncClient, session: AsyncSession):
    token1, user_id1 = await _register_and_get_token(client, "rev_empty1")

    resp = await client.get(f"/api/v1/reviews/users/{user_id1}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 0
    assert data["average_skill"] == 0.0
    assert data["average_punctuality"] == 0.0
    assert data["average_sportsmanship"] == 0.0
    assert len(data["reviews"]) == 0


@pytest.mark.asyncio
async def test_user_reviews_averages_correct(client: AsyncClient, session: AsyncSession):
    """Two revealed reviews should produce correct averages."""
    token1, user_id1 = await _register_and_get_token(client, "rev_avg1")
    token2, user_id2 = await _register_and_get_token(client, "rev_avg2")
    token3, user_id3 = await _register_and_get_token(client, "rev_avg3")
    court = await _seed_court(session)

    # Booking 1: user1 <-> user2
    booking_id1 = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # Both review each other for booking 1
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id1,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "booking_id": booking_id1,
            "reviewee_id": user_id1,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )

    # Booking 2: user1 <-> user3
    booking_id2 = await _create_completed_booking(client, session, token1, token3, str(court.id))

    # Both review each other for booking 2
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id2,
            "reviewee_id": user_id3,
            "skill_rating": 2,
            "punctuality_rating": 2,
            "sportsmanship_rating": 2,
        },
    )
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token3}"},
        json={
            "booking_id": booking_id2,
            "reviewee_id": user_id1,
            "skill_rating": 2,
            "punctuality_rating": 2,
            "sportsmanship_rating": 2,
        },
    )

    # User1 should have 2 revealed reviews with averages: (4+2)/2 = 3.0
    resp = await client.get(f"/api/v1/reviews/users/{user_id1}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 2
    assert data["average_skill"] == 3.0
    assert data["average_punctuality"] == 3.0
    assert data["average_sportsmanship"] == 3.0
    assert len(data["reviews"]) == 2


async def _create_completed_doubles_booking(
    client: AsyncClient,
    session: AsyncSession,
    token1: str,
    token2: str,
    token3: str,
    token4: str,
    court_id: str,
) -> str:
    """Create a 4-person doubles booking, accept all, confirm, backdate, complete. Returns booking_id."""
    # Creator (token1) creates a doubles booking
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": court_id,
            "match_type": "doubles",
            "play_date": _future_date(),
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
            "description": "Doubles review test",
        },
    )
    assert resp.status_code == 201, f"Create doubles booking failed: {resp.json()}"
    booking_id = resp.json()["id"]

    # All three others join
    for token in (token2, token3, token4):
        resp = await client.post(
            f"/api/v1/bookings/{booking_id}/join",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Join failed: {resp.json()}"

    # Creator accepts all pending participants
    detail = await client.get(f"/api/v1/bookings/{booking_id}")
    participants = detail.json()["participants"]
    pending_ids = [p["user_id"] for p in participants if p["status"] == "pending"]
    for joiner_id in pending_ids:
        resp = await client.patch(
            f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
            headers={"Authorization": f"Bearer {token1}"},
            json={"status": "accepted"},
        )
        assert resp.status_code == 200, f"Accept failed: {resp.json()}"

    # Confirm
    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/confirm",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200, f"Confirm failed: {resp.json()}"

    # Backdate play_date to past so complete works
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    # Complete
    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/complete",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200, f"Complete failed: {resp.json()}"
    assert resp.json()["status"] == "completed"

    return booking_id


# --- Gap Tests ---


@pytest.mark.asyncio
async def test_blocked_user_cannot_submit_review(client: AsyncClient, session: AsyncSession):
    """Blocked user should be prevented from reviewing the blocked user."""
    token1, user_id1 = await _register_and_get_token(client, "rev_blk1")
    token2, user_id2 = await _register_and_get_token(client, "rev_blk2")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # user1 blocks user2
    resp = await client.post(
        "/api/v1/blocks",
        headers={"Authorization": f"Bearer {token1}"},
        json={"blocked_id": user_id2},
    )
    assert resp.status_code == 201, f"Block failed: {resp.json()}"

    # user1 now tries to review user2 — should fail because block exists
    resp = await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 5,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code in (400, 403)


@pytest.mark.asyncio
async def test_hidden_reviews_excluded_from_averages(client: AsyncClient, session: AsyncSession):
    """Reviews with is_hidden=True should not count toward averages."""
    token1, user_id1 = await _register_and_get_token(client, "rev_hid1")
    token2, user_id2 = await _register_and_get_token(client, "rev_hid2")
    token3, user_id3 = await _register_and_get_token(client, "rev_hid3")
    court = await _seed_court(session)

    # Booking 1: user1 <-> user2, both review each other (reveals)
    booking_id1 = await _create_completed_booking(client, session, token1, token2, str(court.id))
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id1,
            "reviewee_id": user_id2,
            "skill_rating": 5,
            "punctuality_rating": 5,
            "sportsmanship_rating": 5,
        },
    )
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "booking_id": booking_id1,
            "reviewee_id": user_id1,
            "skill_rating": 5,
            "punctuality_rating": 5,
            "sportsmanship_rating": 5,
        },
    )

    # Booking 2: user1 <-> user3, both review each other (reveals)
    booking_id2 = await _create_completed_booking(client, session, token1, token3, str(court.id))
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id2,
            "reviewee_id": user_id3,
            "skill_rating": 1,
            "punctuality_rating": 1,
            "sportsmanship_rating": 1,
        },
    )
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token3}"},
        json={
            "booking_id": booking_id2,
            "reviewee_id": user_id1,
            "skill_rating": 1,
            "punctuality_rating": 1,
            "sportsmanship_rating": 1,
        },
    )

    # Verify user1 has 2 revealed reviews with average 3.0 before hiding
    averages = await get_review_averages(session, uuid.UUID(user_id1))
    assert averages["total_reviews"] == 2
    assert averages["average_skill"] == 3.0

    # Hide the review from booking2 (the rating=1 one) directly in the DB
    await session.execute(
        update(Review)
        .where(
            Review.booking_id == uuid.UUID(booking_id2),
            Review.reviewee_id == uuid.UUID(user_id1),
        )
        .values(is_hidden=True)
    )
    await session.commit()

    # Now averages should only include the rating=5 review from booking1
    averages = await get_review_averages(session, uuid.UUID(user_id1))
    assert averages["total_reviews"] == 1
    assert averages["average_skill"] == 5.0
    assert averages["average_punctuality"] == 5.0
    assert averages["average_sportsmanship"] == 5.0


@pytest.mark.asyncio
async def test_pending_reviews_four_person_doubles(client: AsyncClient, session: AsyncSession):
    """Each participant in a 4-person completed doubles booking sees 3 pending reviewees."""
    token1, user_id1 = await _register_and_get_token(client, "rev_dbl1")
    token2, user_id2 = await _register_and_get_token(client, "rev_dbl2")
    token3, user_id3 = await _register_and_get_token(client, "rev_dbl3")
    token4, user_id4 = await _register_and_get_token(client, "rev_dbl4")
    court = await _seed_court(session)

    booking_id = await _create_completed_doubles_booking(
        client, session, token1, token2, token3, token4, str(court.id)
    )

    all_user_ids = {user_id1, user_id2, user_id3, user_id4}

    # Each participant should have exactly 3 pending reviewees (all other 3 participants)
    for token, my_user_id in [
        (token1, user_id1),
        (token2, user_id2),
        (token3, user_id3),
        (token4, user_id4),
    ]:
        resp = await client.get(
            "/api/v1/reviews/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Pending for {my_user_id} failed: {resp.json()}"
        data = resp.json()
        assert len(data) == 1, f"User {my_user_id} expected 1 booking pending, got {len(data)}"
        assert data[0]["booking_id"] == booking_id
        reviewee_ids = {r["user_id"] for r in data[0]["reviewees"]}
        expected_ids = all_user_ids - {my_user_id}
        assert reviewee_ids == expected_ids, (
            f"User {my_user_id}: expected reviewees {expected_ids}, got {reviewee_ids}"
        )


@pytest.mark.asyncio
async def test_non_participant_gets_empty_booking_reviews(client: AsyncClient, session: AsyncSession):
    """get_booking_reviews_for_user() returns empty list for user not in booking."""
    token1, user_id1 = await _register_and_get_token(client, "rev_out1")
    token2, user_id2 = await _register_and_get_token(client, "rev_out2")
    token3, user_id3 = await _register_and_get_token(client, "rev_out3")
    court = await _seed_court(session)

    booking_id = await _create_completed_booking(client, session, token1, token2, str(court.id))

    # user1 reviews user2 and user2 reviews user1 so reviews exist in DB
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id2,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    await client.post(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "booking_id": booking_id,
            "reviewee_id": user_id1,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )

    # user3 (outsider) calls the service directly — should get nothing
    result = await get_booking_reviews_for_user(
        session,
        uuid.UUID(booking_id),
        uuid.UUID(user_id3),
    )
    assert result == [], f"Expected empty list for non-participant, got: {result}"
