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


# ---------------------------------------------------------------------------
# Test 4: Suspended user login rejected (username)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suspended_user_login_rejected(client: AsyncClient, session: AsyncSession):
    """Register, suspend via DB, then login → 403."""
    from app.models.user import User as UserModel

    token, uid = await _register_and_get_token(client, "susp_login")

    # Suspend via DB
    user = await session.get(UserModel, uuid.UUID(uid))
    assert user is not None
    user.is_suspended = True
    await session.commit()

    # Login attempt should be rejected with 403
    resp = await client.post(
        "/api/v1/auth/login/username",
        json={"username": "susp_login", "password": "pass1234"},
    )
    assert resp.status_code == 403, (
        f"Expected 403 for suspended user login, got {resp.status_code}: {resp.json()}"
    )


# ---------------------------------------------------------------------------
# Test 5: Suspended user's token rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suspended_user_token_rejected(client: AsyncClient, session: AsyncSession):
    """Register, get token, suspend via DB, call authenticated endpoint → 403."""
    from app.models.user import User as UserModel

    token, uid = await _register_and_get_token(client, "susp_token")

    # Verify token works before suspension
    resp = await client.get("/api/v1/users/me", headers=_auth(token))
    assert resp.status_code == 200, f"Expected 200 before suspension, got {resp.status_code}"

    # Suspend via DB
    user = await session.get(UserModel, uuid.UUID(uid))
    assert user is not None
    user.is_suspended = True
    await session.commit()
    session.expire_all()

    # Token should now be rejected with 403
    resp = await client.get("/api/v1/users/me", headers=_auth(token))
    assert resp.status_code == 403, (
        f"Expected 403 for suspended user token, got {resp.status_code}: {resp.json()}"
    )


# ---------------------------------------------------------------------------
# Test 6: Suspended proposer blocks acceptance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suspended_proposer_blocks_acceptance(client: AsyncClient, session: AsyncSession):
    """Create proposal from A to B, suspend A, B tries to accept → 400."""
    from app.models.user import User as UserModel

    token_a, uid_a = await _register_and_get_token(client, "susp_prop_a")
    token_b, uid_b = await _register_and_get_token(client, "susp_prop_b")
    court = await _seed_court(session)

    # Create a pending proposal directly in DB (A proposes to B)
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
    proposal_id = str(proposal.id)

    # Suspend proposer A
    user_a = await session.get(UserModel, uuid.UUID(uid_a))
    assert user_a is not None
    user_a.is_suspended = True
    await session.commit()
    session.expire_all()

    # B tries to accept → should fail with 400 (proposer suspended)
    resp = await client.patch(
        f"/api/v1/matching/proposals/{proposal_id}",
        headers=_auth(token_b),
        json={"status": "accepted"},
    )
    assert resp.status_code == 400, (
        f"Expected 400 when accepting proposal from suspended proposer, got {resp.status_code}: {resp.json()}"
    )


# ---------------------------------------------------------------------------
# Booking lifecycle tests (Task 23)
# ---------------------------------------------------------------------------

async def _create_booking_raw(
    client: AsyncClient,
    token: str,
    court_id: str,
    match_type: str = "singles",
) -> dict:
    """Create a booking and return the response JSON."""
    resp = await client.post(
        "/api/v1/bookings",
        headers=_auth(token),
        json={
            "court_id": court_id,
            "match_type": match_type,
            "play_date": _future_date(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
        },
    )
    assert resp.status_code == 201, f"Create booking failed: {resp.json()}"
    return resp.json()


# ---------------------------------------------------------------------------
# Test 7: Full happy path — create → join → confirm → complete → review
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_booking_lifecycle_full_happy_path(client: AsyncClient, session: AsyncSession):
    """Full happy path: create → join → confirm → complete → review.

    Verifies:
    - Chat room created on confirm
    - Credit (+5) awarded to both accepted participants on complete
    - Review window is open after complete
    """
    from sqlalchemy import update

    token1, uid1 = await _register_and_get_token(client, "lifecycle_a")
    token2, uid2 = await _register_and_get_token(client, "lifecycle_b")
    court = await _seed_court(session)

    # 1. Create booking (creator auto-joins as ACCEPTED)
    booking = await _create_booking_raw(client, token1, str(court.id))
    booking_id = booking["id"]
    assert booking["status"] == "open"
    assert len(booking["participants"]) == 1
    assert booking["participants"][0]["status"] == "accepted"

    # 2. Second user joins (PENDING)
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    assert resp.status_code == 200, f"Join failed: {resp.json()}"

    # 3. Creator accepts joiner
    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers=_auth(token1),
        json={"status": "accepted"},
    )
    assert resp.status_code == 200, f"Accept failed: {resp.json()}"

    # 4. Confirm booking — chat room should be created
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))
    assert resp.status_code == 200, f"Confirm failed: {resp.json()}"
    assert resp.json()["status"] == "confirmed"

    # Verify chat room was created
    room_result = await session.execute(
        select(ChatRoom).where(ChatRoom.booking_id == uuid.UUID(booking_id))
    )
    room = room_result.scalar_one_or_none()
    assert room is not None, "Chat room should be created on confirm"
    assert room.is_readonly is False, "Chat room should not be readonly after confirm"

    # 5. Backdate play_date so complete is allowed
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    # 6. Complete booking
    resp = await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))
    assert resp.status_code == 200, f"Complete failed: {resp.json()}"
    assert resp.json()["status"] == "completed"

    # Verify credit awarded (+5 each, starting from 80 → 85)
    profile1 = await client.get("/api/v1/users/me", headers=_auth(token1))
    assert profile1.json()["credit_score"] == 85, "Creator should get +5 credit on complete"

    profile2 = await client.get("/api/v1/users/me", headers=_auth(token2))
    assert profile2.json()["credit_score"] == 85, "Joiner should get +5 credit on complete"

    # 7. Review window open — both can submit reviews
    resp = await client.post(
        "/api/v1/reviews",
        headers=_auth(token1),
        json={
            "booking_id": booking_id,
            "reviewee_id": uid2,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    assert resp.status_code == 201, f"Review A→B failed: {resp.json()}"

    resp = await client.post(
        "/api/v1/reviews",
        headers=_auth(token2),
        json={
            "booking_id": booking_id,
            "reviewee_id": uid1,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
    )
    assert resp.status_code == 201, f"Review B→A failed: {resp.json()}"


# ---------------------------------------------------------------------------
# Test 8: Confirm booking creates chat room with correct participants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_creates_chat_room_with_correct_participants(
    client: AsyncClient, session: AsyncSession
):
    """After confirm, the chat room should contain only ACCEPTED participants."""
    token1, uid1 = await _register_and_get_token(client, "chatroom_a")
    token2, uid2 = await _register_and_get_token(client, "chatroom_b")
    token3, uid3 = await _register_and_get_token(client, "chatroom_c")
    court = await _seed_court(session)

    # Create a doubles booking (max 4) so we can have 1 accepted + 1 rejected + creator
    booking = await _create_booking_raw(client, token1, str(court.id), match_type="doubles")
    booking_id = booking["id"]

    # uid2 joins and gets ACCEPTED
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    assert resp.status_code == 200
    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers=_auth(token1),
        json={"status": "accepted"},
    )
    assert resp.status_code == 200

    # uid3 joins and gets REJECTED
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token3))
    assert resp.status_code == 200
    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid3}",
        headers=_auth(token1),
        json={"status": "rejected"},
    )
    assert resp.status_code == 200

    # Confirm — chat room created with ACCEPTED participants only (uid1, uid2)
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))
    assert resp.status_code == 200, f"Confirm failed: {resp.json()}"
    assert resp.json()["status"] == "confirmed"

    # Query chat room
    session.expire_all()
    room_result = await session.execute(
        select(ChatRoom).where(ChatRoom.booking_id == uuid.UUID(booking_id))
    )
    room = room_result.scalar_one_or_none()
    assert room is not None, "Chat room should be created on confirm"
    assert room.type == RoomType.GROUP, "Doubles booking should create GROUP chat room"

    # Query participants of the room
    participants_result = await session.execute(
        select(ChatParticipant).where(ChatParticipant.room_id == room.id)
    )
    room_participant_ids = {str(p.user_id) for p in participants_result.scalars().all()}

    assert uid1 in room_participant_ids, "Creator (ACCEPTED) should be in chat room"
    assert uid2 in room_participant_ids, "Accepted joiner should be in chat room"
    assert uid3 not in room_participant_ids, "Rejected participant should NOT be in chat room"


# ---------------------------------------------------------------------------
# Test 9: Cancel confirmed booking sets chat room readonly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_booking_sets_chat_room_readonly(client: AsyncClient, session: AsyncSession):
    """After a confirmed booking is cancelled by creator, its chat room becomes readonly."""
    token1, uid1 = await _register_and_get_token(client, "cancel_room_a")
    token2, uid2 = await _register_and_get_token(client, "cancel_room_b")
    court = await _seed_court(session)

    # Create, join, accept, confirm
    booking = await _create_booking_raw(client, token1, str(court.id))
    booking_id = booking["id"]

    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    assert resp.status_code == 200
    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers=_auth(token1),
        json={"status": "accepted"},
    )
    assert resp.status_code == 200
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"

    # Verify chat room exists and is writable
    room_result = await session.execute(
        select(ChatRoom).where(ChatRoom.booking_id == uuid.UUID(booking_id))
    )
    room = room_result.scalar_one_or_none()
    assert room is not None, "Chat room should exist after confirm"
    assert room.is_readonly is False, "Chat room should be writable before cancel"

    # Cancel booking (creator cancels whole booking)
    resp = await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=_auth(token1))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # Verify chat room is now readonly
    session.expire_all()
    room_result = await session.execute(
        select(ChatRoom).where(ChatRoom.booking_id == uuid.UUID(booking_id))
    )
    room = room_result.scalar_one_or_none()
    assert room is not None, "Chat room should still exist after cancel"
    assert room.is_readonly is True, "Chat room should be readonly after booking cancellation"


# ---------------------------------------------------------------------------
# Test 10: Complete booking awards credit only to ACCEPTED participants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_booking_awards_credit_to_accepted_only(
    client: AsyncClient, session: AsyncSession
):
    """On complete, only ACCEPTED participants receive +5 credit; REJECTED do not."""
    from sqlalchemy import update

    token1, uid1 = await _register_and_get_token(client, "credit_acc_a")
    token2, uid2 = await _register_and_get_token(client, "credit_acc_b")
    token3, uid3 = await _register_and_get_token(client, "credit_acc_c")
    court = await _seed_court(session)

    # Create doubles booking so we can have 3 participants with different statuses
    booking = await _create_booking_raw(client, token1, str(court.id), match_type="doubles")
    booking_id = booking["id"]

    # uid2 joins and gets ACCEPTED
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    assert resp.status_code == 200
    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers=_auth(token1),
        json={"status": "accepted"},
    )
    assert resp.status_code == 200

    # uid3 joins and gets REJECTED
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token3))
    assert resp.status_code == 200
    resp = await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid3}",
        headers=_auth(token1),
        json={"status": "rejected"},
    )
    assert resp.status_code == 200

    # Confirm with uid1 (creator, ACCEPTED) and uid2 (ACCEPTED) — 2 accepted is enough
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))
    assert resp.status_code == 200, f"Confirm failed: {resp.json()}"

    # Backdate play_date to allow complete
    await session.execute(
        update(Booking)
        .where(Booking.id == uuid.UUID(booking_id))
        .values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()

    # Complete booking
    resp = await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))
    assert resp.status_code == 200, f"Complete failed: {resp.json()}"
    assert resp.json()["status"] == "completed"

    # uid1 (ACCEPTED/creator) should get +5 → 85
    profile1 = await client.get("/api/v1/users/me", headers=_auth(token1))
    assert profile1.json()["credit_score"] == 85, "Creator (ACCEPTED) should get +5 credit"

    # uid2 (ACCEPTED) should get +5 → 85
    profile2 = await client.get("/api/v1/users/me", headers=_auth(token2))
    assert profile2.json()["credit_score"] == 85, "Accepted joiner should get +5 credit"

    # uid3 (REJECTED) should NOT get credit — stays at 80
    profile3 = await client.get("/api/v1/users/me", headers=_auth(token3))
    assert profile3.json()["credit_score"] == 80, "Rejected participant should NOT get credit"
