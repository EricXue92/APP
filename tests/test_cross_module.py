"""Cross-module integration tests focused on block cascade effects."""
import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.chat import ChatRoom, ChatParticipant, RoomType
from app.models.court import Court, CourtType
from app.models.follow import Follow
from app.models.matching import MatchProposal, ProposalStatus
from app.models.review import Review


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_get_token(
    client: AsyncClient, username: str, gender: str = "male", ntrp: str = "3.5"
) -> tuple[str, str]:
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


async def _seed_court(session: AsyncSession) -> Court:
    court = Court(
        name="Cross Module Court",
        address="1 Integration Ave",
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
    uid2: str,
    token2: str,
    court_id: str,
) -> str:
    """Create a singles booking, join, accept, confirm, backdate, complete. Returns booking_id."""
    from sqlalchemy import update

    resp = await client.post(
        "/api/v1/bookings",
        headers=_auth(token1),
        json={
            "court_id": court_id,
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
        },
    )
    assert resp.status_code == 201, f"Create booking failed: {resp.json()}"
    booking_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    assert resp.status_code == 200, f"Join failed: {resp.json()}"

    # Accept joiner
    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers=_auth(token1),
        json={"status": "accepted"},
    )
    assert resp.status_code == 200, f"Accept failed: {resp.json()}"

    # Confirm booking
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))
    assert resp.status_code == 200, f"Confirm failed: {resp.json()}"

    # Backdate play_date so complete works
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    resp = await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))
    assert resp.status_code == 200, f"Complete failed: {resp.json()}"
    assert resp.json()["status"] == "completed"

    return booking_id


# ---------------------------------------------------------------------------
# Test 1: Full block cascade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_block_cascade_full(client: AsyncClient, session: AsyncSession):
    """Block removes follows, hides reviews, sets PRIVATE chat readonly, expires proposals."""
    token_a, uid_a = await _register_and_get_token(client, "cascade_a")
    token_b, uid_b = await _register_and_get_token(client, "cascade_b")
    court = await _seed_court(session)

    # A follows B, B follows A (mutual follows)
    resp = await client.post("/api/v1/follows", json={"followed_id": uid_b}, headers=_auth(token_a))
    assert resp.status_code == 201, f"Follow A→B failed: {resp.json()}"

    resp = await client.post("/api/v1/follows", json={"followed_id": uid_a}, headers=_auth(token_b))
    assert resp.status_code == 201, f"Follow B→A failed: {resp.json()}"

    # Create a completed booking (singles → PRIVATE chat room auto-created on confirm)
    booking_id = await _create_completed_booking(
        client, session, token_a, uid_b, token_b, str(court.id)
    )

    # Both submit reviews
    resp = await client.post(
        "/api/v1/reviews",
        headers=_auth(token_a),
        json={
            "booking_id": booking_id,
            "reviewee_id": uid_b,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    assert resp.status_code == 201, f"Review A→B failed: {resp.json()}"

    resp = await client.post(
        "/api/v1/reviews",
        headers=_auth(token_b),
        json={
            "booking_id": booking_id,
            "reviewee_id": uid_a,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    assert resp.status_code == 201, f"Review B→A failed: {resp.json()}"

    # Create a pending match proposal directly in DB
    play_date = date.today() + timedelta(days=3)
    proposal = MatchProposal(
        proposer_id=uuid.UUID(uid_a),
        target_id=uuid.UUID(uid_b),
        court_id=court.id,
        match_type="singles",
        play_date=play_date,
        start_time=time(10, 0),
        end_time=time(12, 0),
        status=ProposalStatus.PENDING,
    )
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    proposal_id = proposal.id

    # Confirm all cascade targets exist before block
    follows_before = await session.execute(
        select(Follow).where(
            Follow.follower_id.in_([uuid.UUID(uid_a), uuid.UUID(uid_b)]),
            Follow.followed_id.in_([uuid.UUID(uid_a), uuid.UUID(uid_b)]),
        )
    )
    assert len(list(follows_before.scalars().all())) == 2, "Expected 2 mutual follows before block"

    reviews_before = await session.execute(
        select(Review).where(Review.booking_id == uuid.UUID(booking_id))
    )
    assert len(list(reviews_before.scalars().all())) == 2, "Expected 2 reviews before block"

    # Verify proposal is pending
    result = await session.execute(select(MatchProposal).where(MatchProposal.id == proposal_id))
    assert result.scalar_one().status == ProposalStatus.PENDING

    # Verify PRIVATE chat room exists and is not readonly
    chat_room_result = await session.execute(
        select(ChatRoom).where(ChatRoom.booking_id == uuid.UUID(booking_id))
    )
    chat_room = chat_room_result.scalar_one_or_none()
    assert chat_room is not None, "Expected a chat room linked to booking"
    assert chat_room.type == RoomType.PRIVATE, "Expected PRIVATE room for singles booking"
    assert chat_room.is_readonly is False, "Chat room should be writable before block"

    # --- A blocks B ---
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid_b}, headers=_auth(token_a))
    assert resp.status_code == 201, f"Block failed: {resp.json()}"

    # Refresh DB state (expire_all is synchronous)
    session.expire_all()

    # 1. Follows should be removed
    follows_after = await session.execute(
        select(Follow).where(
            Follow.follower_id.in_([uuid.UUID(uid_a), uuid.UUID(uid_b)]),
            Follow.followed_id.in_([uuid.UUID(uid_a), uuid.UUID(uid_b)]),
        )
    )
    assert len(list(follows_after.scalars().all())) == 0, "Follows should be removed after block"

    # 2. Reviews should be hidden
    reviews_after = await session.execute(
        select(Review).where(Review.booking_id == uuid.UUID(booking_id))
    )
    reviews = list(reviews_after.scalars().all())
    assert len(reviews) == 2, "Reviews should still exist (just hidden)"
    assert all(r.is_hidden for r in reviews), "All reviews should be hidden after block"

    # 3. PRIVATE chat room should be readonly
    result = await session.execute(select(ChatRoom).where(ChatRoom.booking_id == uuid.UUID(booking_id)))
    room = result.scalar_one()
    assert room.is_readonly is True, "PRIVATE chat room should be readonly after block"

    # 4. Pending proposal should be expired
    result = await session.execute(select(MatchProposal).where(MatchProposal.id == proposal_id))
    assert result.scalar_one().status == ProposalStatus.EXPIRED, "Proposal should be expired after block"


# ---------------------------------------------------------------------------
# Test 2: Block filters blocked user's bookings from listing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_block_filters_bookings_from_listing(client: AsyncClient, session: AsyncSession):
    """After B blocks A, A's open booking should not appear in B's booking listing."""
    token_a, uid_a = await _register_and_get_token(client, "bklist_a")
    token_b, uid_b = await _register_and_get_token(client, "bklist_b")
    court = await _seed_court(session)

    # A creates an open booking
    resp = await client.post(
        "/api/v1/bookings",
        headers=_auth(token_a),
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
    assert resp.status_code == 201, f"Create booking failed: {resp.json()}"

    # B can see the booking before block
    resp = await client.get("/api/v1/bookings", headers=_auth(token_b))
    assert resp.status_code == 200
    assert len(resp.json()) >= 1, "B should see A's booking before block"

    # B blocks A
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid_a}, headers=_auth(token_b))
    assert resp.status_code == 201, f"Block failed: {resp.json()}"

    # B's listing should now exclude A's booking
    resp = await client.get("/api/v1/bookings", headers=_auth(token_b))
    assert resp.status_code == 200
    bookings = resp.json()
    booking_creator_ids = [b.get("creator_id") for b in bookings]
    assert uid_a not in booking_creator_ids, "A's booking should be hidden from B after block"


# ---------------------------------------------------------------------------
# Test 3: Block prevents review submission
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_block_prevents_review_submission(client: AsyncClient, session: AsyncSession):
    """After A blocks B, B cannot submit a review for the completed booking."""
    token_a, uid_a = await _register_and_get_token(client, "blkrev_a")
    token_b, uid_b = await _register_and_get_token(client, "blkrev_b")
    court = await _seed_court(session)

    # Create a completed booking between A and B
    booking_id = await _create_completed_booking(
        client, session, token_a, uid_b, token_b, str(court.id)
    )

    # A blocks B
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid_b}, headers=_auth(token_a))
    assert resp.status_code == 201, f"Block failed: {resp.json()}"

    # B tries to submit a review for A → should be rejected (block is symmetric)
    resp = await client.post(
        "/api/v1/reviews",
        headers=_auth(token_b),
        json={
            "booking_id": booking_id,
            "reviewee_id": uid_a,
            "skill_rating": 3,
            "punctuality_rating": 3,
            "sportsmanship_rating": 3,
        },
    )
    assert resp.status_code in (400, 403), (
        f"Expected 400 or 403 when blocked user submits review, got {resp.status_code}: {resp.json()}"
    )
