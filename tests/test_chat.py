import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, MatchType, GenderRequirement, ParticipantStatus
from app.models.chat import ChatRoom, RoomType
from app.models.court import Court, CourtType
from app.models.user import User, Gender
from app.services.chat import create_chat_room, get_rooms_for_user, get_room_by_id, add_participant, remove_participant, set_room_readonly


async def _create_user(session: AsyncSession, nickname: str) -> User:
    user = User(
        nickname=nickname,
        gender=Gender.MALE,
        city="Hong Kong",
        ntrp_level="3.5",
        ntrp_label="3.5 中級",
    )
    session.add(user)
    await session.flush()
    return user


async def _create_court(session: AsyncSession) -> Court:
    court = Court(
        name="Victoria Park",
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.flush()
    return court


async def _create_confirmed_booking(session: AsyncSession, creator: User, other: User, court: Court) -> Booking:
    booking = Booking(
        creator_id=creator.id,
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=date.today() + timedelta(days=7),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        gender_requirement=GenderRequirement.ANY,
        max_participants=2,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    await session.flush()
    for user in [creator, other]:
        p = BookingParticipant(booking_id=booking.id, user_id=user.id, status=ParticipantStatus.ACCEPTED)
        session.add(p)
    await session.flush()
    return booking


@pytest.mark.asyncio
async def test_create_chat_room_private(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    room = await create_chat_room(
        session,
        booking=booking,
        participant_ids=[user1.id, user2.id],
        court_name=court.name,
    )
    assert room.type == RoomType.PRIVATE
    assert room.booking_id == booking.id
    assert room.name is None
    assert len(room.participants) == 2


@pytest.mark.asyncio
async def test_create_chat_room_group(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    user3 = await _create_user(session, "Carol")
    court = await _create_court(session)

    booking = Booking(
        creator_id=user1.id,
        court_id=court.id,
        match_type=MatchType.DOUBLES,
        play_date=date.today() + timedelta(days=7),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        gender_requirement=GenderRequirement.ANY,
        max_participants=4,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    await session.flush()
    for user in [user1, user2, user3]:
        p = BookingParticipant(booking_id=booking.id, user_id=user.id, status=ParticipantStatus.ACCEPTED)
        session.add(p)
    await session.flush()

    room = await create_chat_room(
        session,
        booking=booking,
        participant_ids=[user1.id, user2.id, user3.id],
        court_name=court.name,
    )
    assert room.type == RoomType.GROUP
    assert room.name is not None
    assert "Victoria Park" in room.name
    assert len(room.participants) == 3


@pytest.mark.asyncio
async def test_get_rooms_for_user(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)
    rooms = await get_rooms_for_user(session, user1.id)
    assert len(rooms) == 1
    assert rooms[0].booking_id == booking.id


@pytest.mark.asyncio
async def test_set_room_readonly(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)
    assert room.is_readonly is False

    await set_room_readonly(session, booking_id=booking.id)
    await session.refresh(room)
    assert room.is_readonly is True


@pytest.mark.asyncio
async def test_add_remove_participant(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    user3 = await _create_user(session, "Carol")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)
    assert len(room.participants) == 2

    await add_participant(session, room_id=room.id, user_id=user3.id)
    await session.refresh(room)
    room = await get_room_by_id(session, room.id)
    assert len(room.participants) == 3

    await remove_participant(session, room_id=room.id, user_id=user3.id)
    room = await get_room_by_id(session, room.id)
    assert len(room.participants) == 2


from app.services.chat import send_message, get_messages, mark_room_read, get_unread_count


@pytest.mark.asyncio
async def test_send_message(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    msg = await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="Hello!")
    assert msg.content == "Hello!"
    assert msg.sender_id == user1.id
    assert msg.room_id == room.id


@pytest.mark.asyncio
async def test_send_message_blocked_word(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    with pytest.raises(ValueError, match="blocked"):
        await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="你是傻逼")


@pytest.mark.asyncio
async def test_send_message_readonly_room(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    await set_room_readonly(session, booking_id=booking.id)
    with pytest.raises(ValueError, match="read-only"):
        await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="Hi")


@pytest.mark.asyncio
async def test_send_message_not_participant(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    user3 = await _create_user(session, "Carol")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    with pytest.raises(PermissionError):
        await send_message(session, room_id=room.id, sender_id=user3.id, type="text", content="Hi")


@pytest.mark.asyncio
async def test_get_messages_pagination(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    for i in range(5):
        await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content=f"msg {i}")

    messages = await get_messages(session, room_id=room.id, limit=3)
    assert len(messages) == 3
    # Most recent first
    assert messages[0].content == "msg 4"

    # Cursor pagination: get messages before the oldest in first page
    older = await get_messages(session, room_id=room.id, before_id=messages[-1].id, limit=3)
    assert len(older) == 2
    assert older[0].content == "msg 1"


@pytest.mark.asyncio
async def test_unread_count_and_mark_read(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="Hello")
    await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="World")

    count = await get_unread_count(session, room_id=room.id, user_id=user2.id)
    assert count == 2

    await mark_room_read(session, room_id=room.id, user_id=user2.id)
    count = await get_unread_count(session, room_id=room.id, user_id=user2.id)
    assert count == 0


@pytest.mark.asyncio
async def test_image_message_skips_word_filter(session: AsyncSession):
    user1 = await _create_user(session, "Alice")
    user2 = await _create_user(session, "Bob")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)
    room = await create_chat_room(session, booking=booking, participant_ids=[user1.id, user2.id], court_name=court.name)

    # Image content containing blocked word in URL should NOT be filtered
    msg = await send_message(session, room_id=room.id, sender_id=user1.id, type="image", content="https://example.com/傻逼.jpg")
    assert msg.type.value == "image"


# --- REST API Tests ---

async def _register_and_get_token(client: AsyncClient, username: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
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


async def _setup_confirmed_booking_with_room(client: AsyncClient, session: AsyncSession):
    """Create two users, a confirmed booking, and the chat room. Returns (token1, token2, user1_id, user2_id, booking_id, room)."""
    token1, uid1 = await _register_and_get_token(client, "chat_user1")
    token2, uid2 = await _register_and_get_token(client, "chat_user2")
    court = await _seed_court(session)

    # Create booking
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    booking_id = resp.json()["id"]

    # User2 joins
    await client.post(
        f"/api/v1/bookings/{booking_id}/join",
        headers={"Authorization": f"Bearer {token2}"},
    )
    # Creator accepts user2
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )
    # Confirm booking → triggers chat room creation
    await client.post(
        f"/api/v1/bookings/{booking_id}/confirm",
        headers={"Authorization": f"Bearer {token1}"},
    )

    from app.services.chat import get_room_by_booking_id
    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    return token1, token2, uid1, uid2, booking_id, room


@pytest.mark.asyncio
async def test_list_rooms_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.get("/api/v1/chat/rooms", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == str(room.id)
    assert data[0]["unread_count"] == 0


@pytest.mark.asyncio
async def test_send_message_rest_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "Hello from REST!"},
    )
    assert resp.status_code == 201
    assert resp.json()["content"] == "Hello from REST!"


@pytest.mark.asyncio
async def test_get_messages_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    # Send a message first
    await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "Test message"},
    )

    resp = await client.get(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Test message"


@pytest.mark.asyncio
async def test_mark_read_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    # Send message as user1
    await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "Hello"},
    )

    # User2 has 1 unread
    resp = await client.get("/api/v1/chat/rooms", headers={"Authorization": f"Bearer {token2}"})
    assert resp.json()[0]["unread_count"] == 1

    # Mark read
    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/read",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200

    # Unread now 0
    resp = await client.get("/api/v1/chat/rooms", headers={"Authorization": f"Bearer {token2}"})
    assert resp.json()[0]["unread_count"] == 0


@pytest.mark.asyncio
async def test_send_blocked_word_rest_api(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "你是傻逼"},
    )
    assert resp.status_code == 400


# --- Booking Integration Tests ---

from app.services.chat import get_room_by_booking_id


@pytest.mark.asyncio
async def test_confirm_booking_creates_chat_room(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "int_user1")
    token2, uid2 = await _register_and_get_token(client, "int_user2")
    court = await _seed_court(session)

    # Create booking
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    booking_id = resp.json()["id"]

    # User2 joins and gets accepted
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # No room yet
    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    assert room is None

    # Confirm → room should be created
    resp = await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200

    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    assert room is not None
    assert room.type == RoomType.PRIVATE
    assert len(room.participants) == 2


@pytest.mark.asyncio
async def test_cancel_booking_sets_room_readonly(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    assert room.is_readonly is False

    resp = await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200

    await session.refresh(room)
    assert room.is_readonly is True


@pytest.mark.asyncio
async def test_participant_accepted_after_room_exists(client: AsyncClient, session: AsyncSession):
    """For doubles: a late-accepted participant should be added to the chat room."""
    token1, uid1 = await _register_and_get_token(client, "dbl_user1")
    token2, uid2 = await _register_and_get_token(client, "dbl_user2")
    token3, uid3 = await _register_and_get_token(client, "dbl_user3")
    court = await _seed_court(session)

    # Create doubles booking
    resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "court_id": str(court.id),
            "match_type": "doubles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
    )
    booking_id = resp.json()["id"]

    # User2 and User3 join while booking is still OPEN
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token2}"})
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers={"Authorization": f"Bearer {token3}"})

    # Accept user2 only
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Confirm with 2 accepted players (creator + user2) → room created
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers={"Authorization": f"Bearer {token1}"})

    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    assert len(room.participants) == 2

    # Accept user3 AFTER room exists → should be added to chat room
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid3}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"status": "accepted"},
    )

    # Expire cached objects so we get fresh data from DB
    session.expire_all()
    room = await get_room_by_booking_id(session, uuid.UUID(booking_id))
    assert len(room.participants) == 3


# --- WebSocket Tests ---


@pytest.mark.asyncio
async def test_websocket_send_and_receive(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    app = client._transport.app  # noqa: access underlying ASGI app

    # Patch async_session in the chat router to use test DB
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession as AS
    test_engine = create_async_engine("postgresql+asyncpg://postgres:postgres@localhost:5432/lets_tennis_test", echo=False)
    test_session_factory = async_sessionmaker(test_engine, class_=AS, expire_on_commit=False)

    import app.routers.chat as chat_mod
    original = chat_mod.async_session
    chat_mod.async_session = test_session_factory

    from starlette.testclient import TestClient

    try:
        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(f"/api/v1/chat/ws?token={token1}") as ws1:
                # Send ping
                ws1.send_text("ping")
                resp = ws1.receive_text()
                assert resp == "pong"

                # Send a message
                ws1.send_json({
                    "action": "send",
                    "room_id": str(room.id),
                    "type": "text",
                    "content": "Hello via WS!",
                })
                ack = ws1.receive_json()
                assert ack["event"] == "ack"
                assert "id" in ack["data"]
    finally:
        chat_mod.async_session = original
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_websocket_invalid_token(client: AsyncClient, session: AsyncSession):
    app = client._transport.app

    from starlette.testclient import TestClient

    with TestClient(app) as sync_client:
        with pytest.raises(Exception):
            with sync_client.websocket_connect("/api/v1/chat/ws?token=invalid_token"):
                pass


# --- Admin Tests ---

from app.models.user import UserRole


@pytest.mark.asyncio
async def test_admin_delete_message(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    # Send a message
    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "delete me"},
    )
    msg_id = resp.json()["id"]

    # Make user1 an admin
    from app.models.user import User
    user = await session.get(User, uuid.UUID(uid1))
    user.role = UserRole.ADMIN
    await session.commit()

    # Delete message
    resp = await client.delete(
        f"/api/v1/admin/chat/messages/{msg_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 204

    # Verify message is no longer in the room's message list
    resp = await client.get(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
    )
    msg_ids = [m["id"] for m in resp.json()]
    assert msg_id not in msg_ids


@pytest.mark.asyncio
async def test_non_admin_cannot_delete_message(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "keep me"},
    )
    msg_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/admin/chat/messages/{msg_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 403


# --- Block Integration Tests ---


@pytest.mark.asyncio
async def test_block_sets_private_room_readonly(client: AsyncClient, session: AsyncSession):
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    assert room.is_readonly is False

    # User1 blocks User2
    resp = await client.post(
        "/api/v1/blocks",
        headers={"Authorization": f"Bearer {token1}"},
        json={"blocked_id": uid2},
    )
    assert resp.status_code == 201

    await session.refresh(room)
    assert room.is_readonly is True


# --- Edge Case: Send message after being removed from room ---

@pytest.mark.asyncio
async def test_send_message_after_removal(session: AsyncSession):
    """A removed participant should not be able to send messages."""
    from app.services.chat import send_message

    user1 = await _create_user(session, "MsgRemoved1")
    user2 = await _create_user(session, "MsgRemoved2")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    room = await create_chat_room(
        session,
        booking=booking,
        participant_ids=[user1.id, user2.id],
        court_name=court.name,
    )

    # Remove user2
    await remove_participant(session, room_id=room.id, user_id=user2.id)
    await session.commit()

    # user2 tries to send
    with pytest.raises(PermissionError):
        await send_message(
            session,
            room_id=room.id,
            sender_id=user2.id,
            type="text",
            content="Should fail",
        )


# --- Edge Case: Message pagination with non-existent cursor ---

@pytest.mark.asyncio
async def test_message_pagination_bad_cursor(session: AsyncSession):
    """Using a before_id that doesn't exist should return messages from the start."""
    from app.services.chat import send_message, get_messages

    user1 = await _create_user(session, "PagBad1")
    user2 = await _create_user(session, "PagBad2")
    court = await _create_court(session)
    booking = await _create_confirmed_booking(session, user1, user2, court)

    room = await create_chat_room(
        session,
        booking=booking,
        participant_ids=[user1.id, user2.id],
        court_name=court.name,
    )

    # Send a message
    await send_message(session, room_id=room.id, sender_id=user1.id, type="text", content="hello")
    await session.commit()

    # Use a fake before_id — cursor doesn't exist so no filter applied, returns all messages
    messages = await get_messages(session, room_id=room.id, before_id=uuid.uuid4(), limit=10)
    assert len(messages) == 1


# --- Edge Case: Get messages from room user is not part of ---

@pytest.mark.asyncio
async def test_get_messages_not_participant(client: AsyncClient, session: AsyncSession):
    """A non-participant should be denied access to room messages."""
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "Outsider",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": "chat_outsider", "password": "pass1234", "email": "outsider@test.com"},
    )
    outsider_token = resp.json()["access_token"]

    resp = await client.get(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert resp.status_code == 403


# --- Edge Case: Mark read for room user is not part of ---

@pytest.mark.asyncio
async def test_mark_read_not_participant(client: AsyncClient, session: AsyncSession):
    """Marking a room as read when not a participant should return 404."""
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "ReadOutsider",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": "chat_readout", "password": "pass1234", "email": "readout@test.com"},
    )
    outsider_token = resp.json()["access_token"]

    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/read",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert resp.status_code == 404


# --- Edge Case: Send message to readonly room via REST ---

@pytest.mark.asyncio
async def test_send_message_readonly_room_api(client: AsyncClient, session: AsyncSession):
    """Sending via REST to a readonly room should return 400."""
    token1, token2, uid1, uid2, booking_id, room = await _setup_confirmed_booking_with_room(client, session)

    # Set room to readonly
    room.is_readonly = True
    await session.commit()

    resp = await client.post(
        f"/api/v1/chat/rooms/{room.id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={"type": "text", "content": "should fail"},
    )
    assert resp.status_code == 400
