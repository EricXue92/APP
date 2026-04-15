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
