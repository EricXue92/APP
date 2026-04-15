import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventType, EventStatus
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


def _future_deadline() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


@pytest.mark.asyncio
async def test_create_event_chat_room(session: AsyncSession):
    """Test that create_event_chat_room creates a group chat room linked to an event."""
    from app.models.user import Gender
    from app.services.chat import create_event_chat_room

    # Create two users
    user1 = User(nickname="P1", gender=Gender.MALE, city="HK", ntrp_level="3.5", ntrp_label="3.5 中級")
    user2 = User(nickname="P2", gender=Gender.MALE, city="HK", ntrp_level="3.5", ntrp_label="3.5 中級")
    session.add_all([user1, user2])
    await session.flush()

    # Create an event
    event = Event(
        creator_id=user1.id,
        name="Test Tournament",
        event_type=EventType.SINGLES_ELIMINATION,
        min_ntrp="3.0",
        max_ntrp="4.0",
        max_participants=8,
        registration_deadline=datetime.now(timezone.utc) + timedelta(days=7),
        status=EventStatus.IN_PROGRESS,
    )
    session.add(event)
    await session.flush()

    room = await create_event_chat_room(session, event=event, participant_ids=[user1.id, user2.id])

    assert room is not None
    assert room.event_id == event.id
    assert room.name == "Test Tournament"
    assert room.type.value == "group"
    assert len(room.participants) == 2


@pytest.mark.asyncio
async def test_create_event(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "organizer1")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Spring Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "games_per_set": 6,
            "num_sets": 3,
            "match_tiebreak": False,
            "registration_deadline": _future_deadline(),
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Spring Cup"
    assert data["status"] == "draft"
    assert data["event_type"] == "singles_elimination"
    assert data["participant_count"] == 0


@pytest.mark.asyncio
async def test_create_event_credit_too_low(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "lowcred_org")

    from sqlalchemy import update
    await session.execute(update(User).where(User.id == uuid.UUID(user_id)).values(credit_score=70))
    await session.commit()

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Bad Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_event_detail(client: AsyncClient, session: AsyncSession):
    token, user_id = await _register_and_get_token(client, "detail_org")

    create_resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Detail Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Cup"
    assert data["participants"] == []


@pytest.mark.asyncio
async def test_list_events(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "list_org")

    create_resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "List Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = create_resp.json()["id"]

    # Publish it so it shows in listings
    await client.post(
        f"/api/v1/events/{event_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(e["name"] == "List Cup" for e in data)


@pytest.mark.asyncio
async def test_publish_event(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "pub_org")
    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Pub Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/events/{event_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"


@pytest.mark.asyncio
async def test_join_event(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "join_org", ntrp="3.5")
    player_token, _ = await _register_and_get_token(client, "join_player", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Join Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/join",
        headers={"Authorization": f"Bearer {player_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["participant_count"] == 1


@pytest.mark.asyncio
async def test_join_event_ntrp_out_of_range(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "ntrp_org", ntrp="3.5")
    player_token, _ = await _register_and_get_token(client, "ntrp_player", ntrp="5.0")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "NTRP Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/join",
        headers={"Authorization": f"Bearer {player_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_withdraw_from_event(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "wd_org", ntrp="3.5")
    player_token, _ = await _register_and_get_token(client, "wd_player", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "WD Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})
    await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {player_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/withdraw",
        headers={"Authorization": f"Bearer {player_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["participant_count"] == 0


@pytest.mark.asyncio
async def test_start_elimination_event(client: AsyncClient, session: AsyncSession):
    """Start an elimination event with 5 players — should create bracket with BYEs."""
    org_token, _ = await _register_and_get_token(client, "elim_org", ntrp="4.0")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Elim Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Register 5 players
    tokens = []
    for i in range(5):
        ntrp = f"{3.0 + i * 0.25:.1f}"
        tk, _ = await _register_and_get_token(client, f"elim_p{i}", ntrp=ntrp)
        tokens.append(tk)
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    # Start the event
    resp = await client.post(
        f"/api/v1/events/{event_id}/start",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    # Check matches were generated
    resp = await client.get(
        f"/api/v1/events/{event_id}/matches",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    matches = resp.json()
    # 5 players → 8 bracket → 4 first-round + 2 second-round + 1 final = 7 matches
    assert len(matches) == 7
    round1 = [m for m in matches if m["round"] == 1]
    assert len(round1) == 4
    byes = [m for m in round1 if m["player_a_id"] is None or m["player_b_id"] is None]
    assert len(byes) == 3  # 8 - 5 = 3 BYEs


@pytest.mark.asyncio
async def test_start_event_not_enough_participants(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "few_org")
    player_token, _ = await _register_and_get_token(client, "few_p1")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Few Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})
    await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {org_token}"})
    await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {player_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/start",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 400
