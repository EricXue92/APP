import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, MatchType
from app.models.chat import ChatParticipant, ChatRoom, Message, MessageType, RoomType


async def create_chat_room(
    session: AsyncSession,
    *,
    booking: Booking,
    participant_ids: list[uuid.UUID],
    court_name: str,
) -> ChatRoom:
    is_private = booking.match_type == MatchType.SINGLES
    room_type = RoomType.PRIVATE if is_private else RoomType.GROUP

    name = None
    if room_type == RoomType.GROUP:
        date_str = booking.play_date.strftime("%-m/%-d")
        name = f"雙打 @ {court_name} {date_str}"

    room = ChatRoom(
        type=room_type,
        booking_id=booking.id,
        name=name,
    )
    session.add(room)
    await session.flush()

    for uid in participant_ids:
        participant = ChatParticipant(room_id=room.id, user_id=uid)
        session.add(participant)
    await session.flush()

    await session.refresh(room)
    room = await get_room_by_id(session, room.id)
    return room


async def get_room_by_id(session: AsyncSession, room_id: uuid.UUID) -> ChatRoom | None:
    result = await session.execute(
        select(ChatRoom)
        .options(
            selectinload(ChatRoom.participants).selectinload(ChatParticipant.user),
        )
        .where(ChatRoom.id == room_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_room_by_booking_id(session: AsyncSession, booking_id: uuid.UUID) -> ChatRoom | None:
    result = await session.execute(
        select(ChatRoom)
        .options(
            selectinload(ChatRoom.participants).selectinload(ChatParticipant.user),
        )
        .where(ChatRoom.booking_id == booking_id)
    )
    return result.scalar_one_or_none()


async def get_rooms_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[ChatRoom]:
    result = await session.execute(
        select(ChatRoom)
        .join(ChatParticipant, ChatParticipant.room_id == ChatRoom.id)
        .options(
            selectinload(ChatRoom.participants).selectinload(ChatParticipant.user),
        )
        .where(ChatParticipant.user_id == user_id)
        .order_by(ChatRoom.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def set_room_readonly(session: AsyncSession, *, booking_id: uuid.UUID) -> None:
    room = await get_room_by_booking_id(session, booking_id)
    if room:
        room.is_readonly = True
        await session.flush()


async def add_participant(session: AsyncSession, *, room_id: uuid.UUID, user_id: uuid.UUID) -> ChatParticipant:
    participant = ChatParticipant(room_id=room_id, user_id=user_id)
    session.add(participant)
    await session.flush()
    return participant


async def remove_participant(session: AsyncSession, *, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
    result = await session.execute(
        select(ChatParticipant).where(
            ChatParticipant.room_id == room_id,
            ChatParticipant.user_id == user_id,
        )
    )
    participant = result.scalar_one_or_none()
    if participant:
        await session.delete(participant)
        await session.flush()
