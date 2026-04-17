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
async def test_block_nonexistent_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "blockghost")
    fake_id = str(uuid.uuid4())

    resp = await client.post("/api/v1/blocks", json={"blocked_id": fake_id}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_suspended_user_cannot_login(client: AsyncClient, session: AsyncSession):
    """Suspended user should be denied new tokens on login."""
    from app.models.user import User
    from sqlalchemy import update

    token1, uid1 = await _register_and_get_token(client, "suspendlogin")

    await session.execute(
        update(User).where(User.id == uuid.UUID(uid1)).values(is_suspended=True)
    )
    await session.commit()

    resp = await client.post(
        "/api/v1/auth/login/username",
        json={"username": "suspendlogin", "password": "pass1234"},
    )
    assert resp.status_code == 403


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


# --- Gap tests ---


@pytest.mark.asyncio
async def test_is_blocked_all_four_directions(client: AsyncClient, session: AsyncSession):
    """is_blocked() checks both directions: A→B is True and B→A is True after A blocks B."""
    from app.services.block import is_blocked

    token1, uid1 = await _register_and_get_token(client, "isblocked_a")
    token2, uid2 = await _register_and_get_token(client, "isblocked_b")
    token3, uid3 = await _register_and_get_token(client, "isblocked_c")

    uid1 = uuid.UUID(uid1)
    uid2 = uuid.UUID(uid2)
    uid3 = uuid.UUID(uid3)

    # Before any block: neither direction is blocked
    assert await is_blocked(session, uid1, uid2) is False
    assert await is_blocked(session, uid2, uid1) is False

    # A blocks B
    await client.post("/api/v1/blocks", json={"blocked_id": str(uid2)}, headers=_auth(token1))

    # Both directions should return True (symmetric)
    assert await is_blocked(session, uid1, uid2) is True
    assert await is_blocked(session, uid2, uid1) is True

    # Unrelated user C is not blocked
    assert await is_blocked(session, uid1, uid3) is False
    assert await is_blocked(session, uid3, uid1) is False


@pytest.mark.asyncio
async def test_block_expires_pending_proposals(client: AsyncClient, session: AsyncSession):
    """Blocking a user expires any pending match proposals between the two users."""
    from datetime import date, time, timedelta

    from app.models.matching import MatchProposal, ProposalStatus
    from sqlalchemy import select

    token1, uid1 = await _register_and_get_token(client, "propblock_a")
    token2, uid2 = await _register_and_get_token(client, "propblock_b")
    court = await _seed_court(session)

    uid1 = uuid.UUID(uid1)
    uid2 = uuid.UUID(uid2)

    # Create a pending proposal directly in the DB (avoids complex preference setup)
    play_date = date.today() + timedelta(days=3)
    proposal = MatchProposal(
        proposer_id=uid1,
        target_id=uid2,
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

    # Confirm it's pending before block
    result = await session.execute(select(MatchProposal).where(MatchProposal.id == proposal_id))
    pre_block = result.scalar_one()
    assert pre_block.status == ProposalStatus.PENDING

    # A blocks B — should trigger expire_proposals_on_block
    resp = await client.post("/api/v1/blocks", json={"blocked_id": str(uid2)}, headers=_auth(token1))
    assert resp.status_code == 201

    # Proposal should now be EXPIRED
    await session.refresh(pre_block)
    assert pre_block.status == ProposalStatus.EXPIRED


@pytest.mark.asyncio
async def test_mutual_blocks(client: AsyncClient, session: AsyncSession):
    """A blocks B and B blocks A should both succeed (separate records)."""
    token1, uid1 = await _register_and_get_token(client, "mutual_a")
    token2, uid2 = await _register_and_get_token(client, "mutual_b")

    # A blocks B
    resp1 = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp1.status_code == 201

    # B blocks A — should also succeed (independent record)
    resp2 = await client.post("/api/v1/blocks", json={"blocked_id": uid1}, headers=_auth(token2))
    assert resp2.status_code == 201

    # Verify both blocks exist via list endpoint
    list1 = await client.get("/api/v1/blocks", headers=_auth(token1))
    list2 = await client.get("/api/v1/blocks", headers=_auth(token2))
    assert len(list1.json()) == 1
    assert len(list2.json()) == 1


@pytest.mark.asyncio
async def test_block_unblock_reblock(client: AsyncClient, session: AsyncSession):
    """Block → unblock → re-block should succeed with no duplicate constraint error."""
    token1, uid1 = await _register_and_get_token(client, "reblock_a")
    token2, uid2 = await _register_and_get_token(client, "reblock_b")

    # First block
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201

    # Unblock (hard delete)
    resp = await client.delete(f"/api/v1/blocks/{uid2}", headers=_auth(token1))
    assert resp.status_code == 204

    # Re-block — should succeed, no unique constraint violation
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201


# --- Edge Case: Block → reviews hidden → unblock → reviews stay hidden ---

@pytest.mark.asyncio
async def test_block_hides_reviews_permanently(client: AsyncClient, session: AsyncSession):
    """Reviews hidden by a block should remain hidden after unblock."""
    from app.models.review import Review
    from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
    from sqlalchemy.ext.asyncio import AsyncSession

    token1, uid1 = await _register_and_get_token(client, "bhperm_a")
    token2, uid2 = await _register_and_get_token(client, "bhperm_b")
    court = await _seed_court(session)

    # Create a completed booking and mutual reviews
    from datetime import timedelta
    resp = await client.post(
        "/api/v1/bookings",
        headers=_auth(token1),
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": str(date.today() + timedelta(days=7)),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    booking_id = resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    detail = (await client.get(f"/api/v1/bookings/{booking_id}")).json()
    joiner_id = [p["user_id"] for p in detail["participants"] if p["status"] == "pending"][0]
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{joiner_id}",
        headers=_auth(token1),
        json={"status": "accepted"},
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    from sqlalchemy import update as sa_update
    from app.models.booking import Booking as BM
    await session.execute(
        sa_update(BM).where(BM.id == uuid.UUID(booking_id)).values(play_date=date.today() - timedelta(days=1))
    )
    await session.commit()
    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    # Both review each other
    for reviewer_tok, reviewee_id in [(token1, uid2), (token2, uid1)]:
        await client.post(
            "/api/v1/reviews",
            headers=_auth(reviewer_tok),
            json={
                "booking_id": booking_id,
                "reviewee_id": reviewee_id,
                "skill_rating": 4,
                "punctuality_rating": 4,
                "sportsmanship_rating": 4,
            },
        )

    # Verify reviews are visible (revealed)
    resp = await client.get(f"/api/v1/reviews/users/{uid1}")
    assert resp.json()["total_reviews"] == 1

    # Block: should hide mutual reviews
    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    # Reviews should now be hidden
    from sqlalchemy import select, and_, or_
    result = await session.execute(
        select(Review).where(
            or_(
                and_(Review.reviewer_id == uuid.UUID(uid1), Review.reviewee_id == uuid.UUID(uid2)),
                and_(Review.reviewer_id == uuid.UUID(uid2), Review.reviewee_id == uuid.UUID(uid1)),
            )
        )
    )
    reviews = list(result.scalars().all())
    assert all(r.is_hidden for r in reviews), "All mutual reviews should be hidden after block"

    # Unblock
    await client.delete(f"/api/v1/blocks/{uid2}", headers=_auth(token1))

    # Reviews should STILL be hidden (permanence)
    for r in reviews:
        await session.refresh(r)
    assert all(r.is_hidden for r in reviews), "Reviews should remain hidden after unblock"


# --- Edge Case: Block with pending booking invite ---

@pytest.mark.asyncio
async def test_block_does_not_crash_with_pending_invite(client: AsyncClient, session: AsyncSession):
    """Blocking someone with a pending invite should not cause errors."""
    token1, uid1 = await _register_and_get_token(client, "blkinv_a")
    token2, uid2 = await _register_and_get_token(client, "blkinv_b")
    court = await _seed_court(session)

    # Create an invite from A to B
    from datetime import timedelta
    resp = await client.post(
        "/api/v1/bookings/invites",
        headers=_auth(token1),
        json={
            "invitee_id": uid2,
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": str(date.today() + timedelta(days=3)),
            "start_time": "14:00:00",
            "end_time": "16:00:00",
        },
    )
    assert resp.status_code == 201

    # A blocks B — should succeed without crashing
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201


# --- Edge Case: Block nonexistent user ---

@pytest.mark.asyncio
async def test_block_nonexistent_user(client: AsyncClient, session: AsyncSession):
    token1, _ = await _register_and_get_token(client, "blk_nouser")
    fake_id = str(uuid.uuid4())

    resp = await client.post("/api/v1/blocks", json={"blocked_id": fake_id}, headers=_auth(token1))
    assert resp.status_code == 400
