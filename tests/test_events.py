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
