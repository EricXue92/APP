import uuid

from sqlalchemy import func as sa_func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, MatchType
from app.models.chat import ChatParticipant, ChatRoom, Message, MessageType, RoomType
from app.services.word_filter import contains_blocked_word


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
        .execution_options(populate_existing=True)
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


async def send_message(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    sender_id: uuid.UUID,
    type: str,
    content: str,
) -> Message:
    room = await get_room_by_id(session, room_id)
    if room is None:
        raise LookupError("Room not found")

    if room.is_readonly:
        raise ValueError("Room is read-only")

    # Check sender is a participant
    is_participant = any(p.user_id == sender_id for p in room.participants)
    if not is_participant:
        raise PermissionError("Not a participant")

    # Word filter for text messages only
    msg_type = MessageType(type)
    if msg_type == MessageType.TEXT and contains_blocked_word(content):
        raise ValueError("Message contains blocked content")

    message = Message(
        room_id=room_id,
        sender_id=sender_id,
        type=msg_type,
        content=content,
    )
    session.add(message)
    await session.flush()
    await session.refresh(message)
    return message


async def get_messages(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    before_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[Message]:
    query = (
        select(Message)
        .options(selectinload(Message.sender))
        .where(Message.room_id == room_id)
    )
    if before_id:
        # Get the created_at of the cursor message
        cursor_result = await session.execute(
            select(Message.created_at).where(Message.id == before_id)
        )
        cursor_time = cursor_result.scalar_one_or_none()
        if cursor_time:
            query = query.where(Message.created_at < cursor_time)

    query = query.order_by(Message.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_unread_count(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int:
    # Get the user's last_read_at for this room
    result = await session.execute(
        select(ChatParticipant.last_read_at).where(
            ChatParticipant.room_id == room_id,
            ChatParticipant.user_id == user_id,
        )
    )
    last_read = result.scalar_one_or_none()

    count_query = select(sa_func.count(Message.id)).where(Message.room_id == room_id)
    if last_read is not None:
        count_query = count_query.where(Message.created_at > last_read)

    result = await session.execute(count_query)
    return result.scalar_one()


async def mark_room_read(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(ChatParticipant).where(
            ChatParticipant.room_id == room_id,
            ChatParticipant.user_id == user_id,
        )
    )
    participant = result.scalar_one_or_none()
    if participant is None:
        raise LookupError("Not a participant")
    participant.last_read_at = text("clock_timestamp()")
    await session.flush()
