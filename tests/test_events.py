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


@pytest.mark.asyncio
async def test_start_round_robin_event(client: AsyncClient, session: AsyncSession):
    """Start a round-robin event with 6 players — should create groups and matches."""
    org_token, _ = await _register_and_get_token(client, "rr_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "RR Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    for i in range(6):
        tk, _ = await _register_and_get_token(client, f"rr_p{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/start",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    resp = await client.get(
        f"/api/v1/events/{event_id}/matches",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    matches = resp.json()

    # 6 players → 2 groups of 3 → each group has C(3,2) = 3 matches → 6 total
    assert len(matches) == 6

    groups = set(m["group_name"] for m in matches)
    assert len(groups) == 2
    assert "A" in groups
    assert "B" in groups


@pytest.mark.asyncio
async def test_submit_score(client: AsyncClient, session: AsyncSession):
    """Submit a valid score for a round-robin match."""
    org_token, org_id = await _register_and_get_token(client, "sc_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Score Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"sc_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    matches = resp.json()
    match_id = matches[0]["id"]
    submitter_id = matches[0]["player_a_id"]

    submitter_token = next(tk for tk, pid in player_tokens if pid == submitter_id)

    # Submit score: 6-4 6-3 (player A wins in 2 sets)
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {submitter_token}"},
        json={
            "sets": [
                {"set_number": 1, "score_a": 6, "score_b": 4},
                {"set_number": 2, "score_a": 6, "score_b": 3},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"
    assert data["winner_id"] == submitter_id
    assert len(data["sets"]) == 2


@pytest.mark.asyncio
async def test_submit_score_invalid(client: AsyncClient, session: AsyncSession):
    """Submit an invalid score (e.g., 6-5 without tiebreak) — should fail."""
    org_token, _ = await _register_and_get_token(client, "inv_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Invalid Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"inv_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match_id = resp.json()[0]["id"]
    submitter_id = resp.json()[0]["player_a_id"]
    submitter_token = next(tk for tk, pid in player_tokens if pid == submitter_id)

    # Invalid: 6-5 without tiebreak
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {submitter_token}"},
        json={
            "sets": [
                {"set_number": 1, "score_a": 6, "score_b": 5},
            ]
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_confirm_score(client: AsyncClient, session: AsyncSession):
    """After submitting, the opponent confirms the score."""
    org_token, _ = await _register_and_get_token(client, "cf_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Confirm Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"cf_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match = resp.json()[0]
    match_id = match["id"]

    # Find tokens for both players
    a_token = next(tk for tk, pid in player_tokens if pid == match["player_a_id"])
    b_token = next(tk for tk, pid in player_tokens if pid == match["player_b_id"])

    # Player A submits
    await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {a_token}"},
        json={"sets": [{"set_number": 1, "score_a": 6, "score_b": 4}, {"set_number": 2, "score_a": 6, "score_b": 3}]},
    )

    # Player B confirms
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/confirm",
        headers={"Authorization": f"Bearer {b_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    assert resp.json()["confirmed_at"] is not None


@pytest.mark.asyncio
async def test_dispute_score(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "dp_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Dispute Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"dp_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match = resp.json()[0]
    match_id = match["id"]
    a_token = next(tk for tk, pid in player_tokens if pid == match["player_a_id"])
    b_token = next(tk for tk, pid in player_tokens if pid == match["player_b_id"])

    await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {a_token}"},
        json={"sets": [{"set_number": 1, "score_a": 6, "score_b": 4}, {"set_number": 2, "score_a": 6, "score_b": 3}]},
    )

    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/dispute",
        headers={"Authorization": f"Bearer {b_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "disputed"


@pytest.mark.asyncio
async def test_walkover(client: AsyncClient, session: AsyncSession):
    """Submit a walkover — absent player gets credit penalty."""
    org_token, _ = await _register_and_get_token(client, "wo_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "WO Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"wo_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match = resp.json()[0]
    match_id = match["id"]
    a_token = next(tk for tk, pid in player_tokens if pid == match["player_a_id"])

    # Player A reports player B as absent
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/walkover",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"  # Needs opponent/organizer confirmation


@pytest.mark.asyncio
async def test_organizer_override_score(client: AsyncClient, session: AsyncSession):
    """Organizer can directly set/override a match score."""
    org_token, org_id = await _register_and_get_token(client, "ov_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Override Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "games_per_set": 6,
            "num_sets": 3,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    player_tokens = []
    for i in range(3):
        tk, pid = await _register_and_get_token(client, f"ov_p{i}", ntrp="3.5")
        player_tokens.append((tk, pid))
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(f"/api/v1/events/{event_id}/matches", headers={"Authorization": f"Bearer {org_token}"})
    match = resp.json()[0]
    match_id = match["id"]

    # Organizer directly sets score (no confirmation needed)
    resp = await client.patch(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {org_token}"},
        json={"sets": [{"set_number": 1, "score_a": 6, "score_b": 2}, {"set_number": 2, "score_a": 6, "score_b": 1}]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_get_bracket(client: AsyncClient, session: AsyncSession):
    """Get elimination bracket as tree structure."""
    org_token, _ = await _register_and_get_token(client, "br_org", ntrp="4.0")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Bracket Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    for i in range(4):
        tk, _ = await _register_and_get_token(client, f"br_p{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(
        f"/api/v1/events/{event_id}/bracket",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    bracket = resp.json()
    assert "rounds" in bracket
    assert len(bracket["rounds"]) >= 2  # At least 2 rounds for 4 players


@pytest.mark.asyncio
async def test_get_standings(client: AsyncClient, session: AsyncSession):
    """Get round-robin standings."""
    org_token, _ = await _register_and_get_token(client, "st_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Standings Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 6,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    for i in range(3):
        tk, _ = await _register_and_get_token(client, f"st_p{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(
        f"/api/v1/events/{event_id}/standings",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200
    standings = resp.json()
    assert len(standings) == 3  # 3 players in 1 group
    assert all("wins" in s and "losses" in s and "points" in s for s in standings)


@pytest.mark.asyncio
async def test_cancel_event(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "can_org")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Cancel Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Join a player
    player_token, _ = await _register_and_get_token(client, "can_p1", ntrp="3.5")
    await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {player_token}"})

    resp = await client.post(
        f"/api/v1/events/{event_id}/cancel",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Score validation unit tests (pure functions, no DB)
# ---------------------------------------------------------------------------

from app.services.event import validate_set_score, validate_match_score


# --- validate_set_score ---

def test_set_score_normal_win():
    assert validate_set_score(6, 4, None, None, 6) is True
    assert validate_set_score(6, 0, None, None, 6) is True
    assert validate_set_score(6, 3, None, None, 6) is True


def test_set_score_normal_win_wrong_margin():
    """6-5 is not valid without tiebreak."""
    assert validate_set_score(6, 5, None, None, 6) is False


def test_set_score_tiebreak_valid():
    assert validate_set_score(7, 6, 7, 5, 6) is True
    assert validate_set_score(7, 6, 9, 7, 6) is True


def test_set_score_tiebreak_invalid_margin():
    """Tiebreak must be won by 2."""
    assert validate_set_score(7, 6, 7, 6, 6) is False


def test_set_score_tiebreak_too_low():
    """Tiebreak winner must reach at least 7."""
    assert validate_set_score(7, 6, 6, 4, 6) is False


def test_set_score_tiebreak_without_7_6():
    """Tiebreak scores only valid with 7-6 game score."""
    assert validate_set_score(6, 4, 7, 5, 6) is False


def test_set_score_6_6_invalid():
    assert validate_set_score(6, 6, None, None, 6) is False


def test_match_tiebreak_valid():
    assert validate_set_score(1, 0, 10, 8, 6, is_match_tiebreak=True) is True
    assert validate_set_score(0, 1, 5, 10, 6, is_match_tiebreak=True) is True


def test_match_tiebreak_not_enough():
    """Match tiebreak winner must reach 10."""
    assert validate_set_score(1, 0, 8, 6, 6, is_match_tiebreak=True) is False


def test_match_tiebreak_margin():
    """Match tiebreak must be won by 2."""
    assert validate_set_score(1, 0, 10, 9, 6, is_match_tiebreak=True) is False


# --- validate_match_score ---

def test_match_score_straight_sets():
    sets = [
        {"score_a": 6, "score_b": 4},
        {"score_a": 6, "score_b": 3},
    ]
    assert validate_match_score(sets, 6, 3, False) == "a"


def test_match_score_three_sets():
    sets = [
        {"score_a": 4, "score_b": 6},
        {"score_a": 6, "score_b": 3},
        {"score_a": 6, "score_b": 4},
    ]
    assert validate_match_score(sets, 6, 3, False) == "a"


def test_match_score_b_wins():
    sets = [
        {"score_a": 3, "score_b": 6},
        {"score_a": 4, "score_b": 6},
    ]
    assert validate_match_score(sets, 6, 3, False) == "b"


def test_match_score_deciding_match_tiebreak():
    sets = [
        {"score_a": 6, "score_b": 4},
        {"score_a": 4, "score_b": 6},
        {"score_a": 1, "score_b": 0, "tiebreak_a": 10, "tiebreak_b": 7},
    ]
    assert validate_match_score(sets, 6, 3, True) == "a"


def test_match_score_invalid_set():
    sets = [
        {"score_a": 5, "score_b": 5},
    ]
    assert validate_match_score(sets, 6, 3, False) is None


def test_match_score_incomplete():
    """One set is not enough to win best-of-3."""
    sets = [
        {"score_a": 6, "score_b": 4},
    ]
    assert validate_match_score(sets, 6, 3, False) is None


# ---------------------------------------------------------------------------
# Lifecycle edge case tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_non_open_event(client: AsyncClient, session: AsyncSession):
    """Joining an in-progress event should fail with 400."""
    org_token, _ = await _register_and_get_token(client, "lc_org1", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "InProg Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Add enough players to start (need 4 for elimination)
    for i in range(4):
        tk, _ = await _register_and_get_token(client, f"lc_sp{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    # Start the event → now in_progress
    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    # New player tries to join an in-progress event
    late_token, _ = await _register_and_get_token(client, "lc_late1", ntrp="3.5")
    resp = await client.post(
        f"/api/v1/events/{event_id}/join",
        headers={"Authorization": f"Bearer {late_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_join_full_event(client: AsyncClient, session: AsyncSession):
    """Joining when max_participants is reached should fail with 409."""
    org_token, _ = await _register_and_get_token(client, "full_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Full Cup",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 4,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Fill the event to capacity (4 players)
    for i in range(4):
        tk, _ = await _register_and_get_token(client, f"full_p{i}", ntrp="3.5")
        r = await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})
        assert r.status_code == 200

    # 5th player tries to join
    extra_token, _ = await _register_and_get_token(client, "full_extra", ntrp="3.5")
    resp = await client.post(
        f"/api/v1/events/{event_id}/join",
        headers={"Authorization": f"Bearer {extra_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_join_at_exact_min_ntrp(client: AsyncClient, session: AsyncSession):
    """Player with NTRP equal to event min_ntrp should be allowed in."""
    org_token, _ = await _register_and_get_token(client, "mintrp_org", ntrp="4.0")
    player_token, _ = await _register_and_get_token(client, "mintrp_player", ntrp="3.0")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "MinNTRP Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
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


@pytest.mark.asyncio
async def test_join_above_max_ntrp(client: AsyncClient, session: AsyncSession):
    """Player with NTRP above event max_ntrp should be rejected with 403."""
    org_token, _ = await _register_and_get_token(client, "maxtrp_org", ntrp="3.5")
    # Player has NTRP 4.5 which exceeds the event max of 4.0
    player_token, _ = await _register_and_get_token(client, "maxtrp_player", ntrp="4.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "MaxNTRP Cup",
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
async def test_withdraw_from_in_progress_event(client: AsyncClient, session: AsyncSession):
    """Withdrawing from an in-progress event should fail with 400."""
    org_token, _ = await _register_and_get_token(client, "wd2_org", ntrp="3.5")
    player_token, _ = await _register_and_get_token(client, "wd2_player", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "WD2 Cup",
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

    # Add more players and start
    for i in range(3):
        tk, _ = await _register_and_get_token(client, f"wd2_fill{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})
    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    # Player tries to withdraw after event started
    resp = await client.post(
        f"/api/v1/events/{event_id}/withdraw",
        headers={"Authorization": f"Bearer {player_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cancel_already_cancelled_event(client: AsyncClient, session: AsyncSession):
    """Cancelling an already-cancelled event should fail with 400."""
    org_token, _ = await _register_and_get_token(client, "cc_org", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "CC Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # First cancel — should succeed
    resp = await client.post(
        f"/api/v1/events/{event_id}/cancel",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 200

    # Second cancel — should fail
    resp = await client.post(
        f"/api/v1/events/{event_id}/cancel",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_my_events(client: AsyncClient, session: AsyncSession):
    """GET /api/v1/events/my returns events the user created and joined."""
    org_token, _ = await _register_and_get_token(client, "my_org", ntrp="3.5")
    joiner_token, _ = await _register_and_get_token(client, "my_joiner", ntrp="3.5")

    # Organizer creates event A
    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "My Event A",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_a_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_a_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Organizer creates event B
    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "My Event B",
            "event_type": "round_robin",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_b_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_b_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    # Joiner joins event A only
    await client.post(f"/api/v1/events/{event_a_id}/join", headers={"Authorization": f"Bearer {joiner_token}"})

    # Organizer's /my should show both events
    resp = await client.get("/api/v1/events/my", headers={"Authorization": f"Bearer {org_token}"})
    assert resp.status_code == 200
    my_events = resp.json()
    my_ids = [e["id"] for e in my_events]
    assert event_a_id in my_ids
    assert event_b_id in my_ids

    # Joiner's /my should show only event A
    resp = await client.get("/api/v1/events/my", headers={"Authorization": f"Bearer {joiner_token}"})
    assert resp.status_code == 200
    joiner_events = resp.json()
    joiner_ids = [e["id"] for e in joiner_events]
    assert event_a_id in joiner_ids
    assert event_b_id not in joiner_ids


@pytest.mark.asyncio
async def test_get_standings_for_elimination_event(client: AsyncClient, session: AsyncSession):
    """GET /standings on an elimination event should return an empty list (graceful)."""
    org_token, _ = await _register_and_get_token(client, "estd_org", ntrp="4.0")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Elim Standings Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    for i in range(4):
        tk, _ = await _register_and_get_token(client, f"estd_p{i}", ntrp="3.5")
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})

    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.get(
        f"/api/v1/events/{event_id}/standings",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    # Elimination events don't use standings — should return 200 with empty list
    assert resp.status_code == 200
    standings = resp.json()
    assert isinstance(standings, list)


# --- Edge Case: Score submit by non-match-participant ---

@pytest.mark.asyncio
async def test_submit_score_by_non_participant(client: AsyncClient, session: AsyncSession):
    """A user not in the match should get 403 when submitting a score."""
    org_token, _ = await _register_and_get_token(client, "sc_nonp_org", ntrp="4.0")
    tokens = []
    for i in range(4):
        tk, _ = await _register_and_get_token(client, f"sc_nonp_p{i}", ntrp="3.5")
        tokens.append(tk)

    # Create, publish, join, start
    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "NonP Score Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})
    for tk in tokens:
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})
    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    # Get first round match
    resp = await client.get(
        f"/api/v1/events/{event_id}/matches?round=1",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    matches = resp.json()
    match_with_two_players = next((m for m in matches if m["player_a_id"] and m["player_b_id"]), None)
    assert match_with_two_players is not None
    match_id = match_with_two_players["id"]

    # Organizer (who is NOT a player in the match) tries to submit score via POST
    # (not the PATCH organizer override)
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {org_token}"},
        json={"sets": [{"set_number": 1, "score_a": 6, "score_b": 4}, {"set_number": 2, "score_a": 6, "score_b": 3}]},
    )
    assert resp.status_code == 403


# --- Edge Case: Confirm score by the wrong player ---

@pytest.mark.asyncio
async def test_confirm_score_by_submitter(client: AsyncClient, session: AsyncSession):
    """The player who submitted the score should not be able to confirm it themselves."""
    org_token, _ = await _register_and_get_token(client, "sc_conf_org", ntrp="4.0")
    tokens_and_ids = []
    for i in range(4):
        tk, uid = await _register_and_get_token(client, f"sc_conf_p{i}", ntrp="3.5")
        tokens_and_ids.append((tk, uid))

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Confirm Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.5",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})
    for tk, _ in tokens_and_ids:
        await client.post(f"/api/v1/events/{event_id}/join", headers={"Authorization": f"Bearer {tk}"})
    await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {org_token}"})

    # Get a match
    resp = await client.get(
        f"/api/v1/events/{event_id}/matches?round=1",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    matches = resp.json()
    match_with_two = next((m for m in matches if m["player_a_id"] and m["player_b_id"]), None)
    assert match_with_two is not None
    match_id = match_with_two["id"]
    player_a_id = match_with_two["player_a_id"]

    # Find player_a's token
    player_a_token = next(tk for tk, uid in tokens_and_ids if uid == player_a_id)

    # Player A submits score
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/score",
        headers={"Authorization": f"Bearer {player_a_token}"},
        json={"sets": [{"set_number": 1, "score_a": 6, "score_b": 4}, {"set_number": 2, "score_a": 6, "score_b": 3}]},
    )
    assert resp.status_code == 200

    # Player A tries to confirm their own submission — should fail
    resp = await client.post(
        f"/api/v1/events/matches/{match_id}/confirm",
        headers={"Authorization": f"Bearer {player_a_token}"},
    )
    assert resp.status_code in (400, 403)


# --- Edge Case: Non-creator tries to start event ---

@pytest.mark.asyncio
async def test_non_creator_cannot_start_event(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "start_org", ntrp="3.5")
    other_token, _ = await _register_and_get_token(client, "start_other", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Start Auth Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.post(f"/api/v1/events/{event_id}/start", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 403


# --- Edge Case: Non-creator tries to cancel event ---

@pytest.mark.asyncio
async def test_non_creator_cannot_cancel_event(client: AsyncClient, session: AsyncSession):
    org_token, _ = await _register_and_get_token(client, "cancel_org", ntrp="3.5")
    other_token, _ = await _register_and_get_token(client, "cancel_other", ntrp="3.5")

    resp = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {org_token}"},
        json={
            "name": "Cancel Auth Cup",
            "event_type": "singles_elimination",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "max_participants": 8,
            "registration_deadline": _future_deadline(),
        },
    )
    event_id = resp.json()["id"]
    await client.post(f"/api/v1/events/{event_id}/publish", headers={"Authorization": f"Bearer {org_token}"})

    resp = await client.post(f"/api/v1/events/{event_id}/cancel", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 403


# --- Edge Case: Get nonexistent event ---

@pytest.mark.asyncio
async def test_get_nonexistent_event(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "noev")
    fake_id = str(uuid.uuid4())

    resp = await client.get(f"/api/v1/events/{fake_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
