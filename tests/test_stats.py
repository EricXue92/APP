import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, MatchType, ParticipantStatus
from app.models.court import Court, CourtType
from app.models.user import User


async def _register_and_get_token(client: AsyncClient, username: str, ntrp: str = "3.5") -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": "male",
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


async def _seed_completed_booking(
    session: AsyncSession,
    court: Court,
    user_ids: list[uuid.UUID],
    play_date: date | None = None,
    match_type: MatchType = MatchType.SINGLES,
) -> Booking:
    """Create a completed booking with accepted participants."""
    booking = Booking(
        creator_id=user_ids[0],
        court_id=court.id,
        match_type=match_type,
        play_date=play_date or date.today(),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        max_participants=2 if match_type == MatchType.SINGLES else 4,
        status=BookingStatus.COMPLETED,
    )
    session.add(booking)
    await session.flush()

    for uid in user_ids:
        participant = BookingParticipant(
            booking_id=booking.id,
            user_id=uid,
            status=ParticipantStatus.ACCEPTED,
        )
        session.add(participant)

    await session.commit()
    await session.refresh(booking)
    return booking


# --- Stats endpoint tests ---


@pytest.mark.asyncio
async def test_stats_no_matches(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "lonely")
    resp = await client.get(
        f"/api/v1/users/{user_id}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_matches"] == 0
    assert data["monthly_matches"] == 0
    assert data["singles_count"] == 0
    assert data["doubles_count"] == 0
    assert data["top_courts"] == []
    assert data["top_partners"] == []


@pytest.mark.asyncio
async def test_stats_with_completed_matches(client: AsyncClient, session: AsyncSession):
    token_a, uid_a = await _register_and_get_token(client, "alice")
    _, uid_b = await _register_and_get_token(client, "bob")
    court = await _seed_court(session)

    await _seed_completed_booking(session, court, [uuid.UUID(uid_a), uuid.UUID(uid_b)])
    await _seed_completed_booking(
        session, court, [uuid.UUID(uid_a), uuid.UUID(uid_b)], match_type=MatchType.DOUBLES
    )

    resp = await client.get(
        f"/api/v1/users/{uid_a}/stats",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_matches"] == 2
    assert data["singles_count"] == 1
    assert data["doubles_count"] == 1


@pytest.mark.asyncio
async def test_stats_top_courts_ranking(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "courtfan")
    _, uid_b = await _register_and_get_token(client, "partner1")
    court_a = await _seed_court(session, "Court Alpha")
    court_b = await _seed_court(session, "Court Beta")
    court_c = await _seed_court(session, "Court Gamma")
    court_d = await _seed_court(session, "Court Delta")

    uids = [uuid.UUID(uid), uuid.UUID(uid_b)]
    # Court Alpha: 3 matches, Court Beta: 2, Court Gamma: 1, Court Delta: 1
    for _ in range(3):
        await _seed_completed_booking(session, court_a, uids)
    for _ in range(2):
        await _seed_completed_booking(session, court_b, uids)
    await _seed_completed_booking(session, court_c, uids)
    await _seed_completed_booking(session, court_d, uids)

    resp = await client.get(
        f"/api/v1/users/{uid}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    courts = data["top_courts"]
    assert len(courts) == 3
    assert courts[0]["court_name"] == "Court Alpha"
    assert courts[0]["match_count"] == 3
    assert courts[1]["court_name"] == "Court Beta"
    assert courts[1]["match_count"] == 2


@pytest.mark.asyncio
async def test_stats_top_partners_ranking(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "social")
    _, uid_b = await _register_and_get_token(client, "freq_partner")
    _, uid_c = await _register_and_get_token(client, "rare_partner")
    court = await _seed_court(session)

    # freq_partner: 3 matches, rare_partner: 1 match
    for _ in range(3):
        await _seed_completed_booking(session, court, [uuid.UUID(uid), uuid.UUID(uid_b)])
    await _seed_completed_booking(session, court, [uuid.UUID(uid), uuid.UUID(uid_c)])

    resp = await client.get(
        f"/api/v1/users/{uid}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    partners = data["top_partners"]
    assert len(partners) == 2
    assert partners[0]["nickname"] == "Player_freq_partner"
    assert partners[0]["match_count"] == 3
    assert partners[1]["nickname"] == "Player_rare_partner"
    assert partners[1]["match_count"] == 1
    # Ensure self is not in partners list
    partner_ids = [p["user_id"] for p in partners]
    assert uid not in partner_ids


@pytest.mark.asyncio
async def test_stats_monthly_matches(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "monthly")
    _, uid_b = await _register_and_get_token(client, "monthly_b")
    court = await _seed_court(session)
    uids = [uuid.UUID(uid), uuid.UUID(uid_b)]

    # One match this month, one match last month
    await _seed_completed_booking(session, court, uids, play_date=date.today())
    last_month = date.today().replace(day=1) - timedelta(days=1)
    await _seed_completed_booking(session, court, uids, play_date=last_month)

    resp = await client.get(
        f"/api/v1/users/{uid}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert data["total_matches"] == 2
    assert data["monthly_matches"] == 1
