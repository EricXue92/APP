import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.chat import MessageResponse, RoomResponse, ParticipantInfo, SendMessageRequest
from app.services.chat import (
    get_messages,
    get_room_by_id,
    get_rooms_for_user,
    get_unread_count,
    mark_room_read,
    send_message,
)
from app.services.block import is_blocked

router = APIRouter()


def _last_message_to_response(msg) -> MessageResponse | None:
    if msg is None:
        return None
    return MessageResponse(
        id=msg.id,
        room_id=msg.room_id,
        sender_id=msg.sender_id,
        sender_nickname=msg.sender.nickname if msg.sender else None,
        type=msg.type.value,
        content=msg.content,
        is_deleted=msg.is_deleted,
        created_at=msg.created_at,
    )


@router.get("/rooms", response_model=list[RoomResponse])
async def list_rooms(user: CurrentUser, session: DbSession):
    rooms = await get_rooms_for_user(session, user.id)
    result = []
    for room in rooms:
        # Block filtering: skip private rooms where other user is blocked
        if room.type.value == "private":
            other_ids = [p.user_id for p in room.participants if p.user_id != user.id]
            if other_ids and await is_blocked(session, user.id, other_ids[0]):
                continue

        # Get last message
        messages = await get_messages(session, room_id=room.id, limit=1)
        last_msg = messages[0] if messages else None

        unread = await get_unread_count(session, room_id=room.id, user_id=user.id)

        participants = [
            ParticipantInfo(
                user_id=p.user_id,
                nickname=p.user.nickname,
                avatar_url=p.user.avatar_url,
            )
            for p in room.participants
        ]

        result.append(RoomResponse(
            id=room.id,
            type=room.type.value,
            name=room.name,
            booking_id=room.booking_id,
            is_readonly=room.is_readonly,
            participants=participants,
            last_message=_last_message_to_response(last_msg),
            unread_count=unread,
            created_at=room.created_at,
        ))
    return result


@router.get("/rooms/{room_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    room_id: str,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
    before: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    room = await get_room_by_id(session, uuid.UUID(room_id))
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("chat.room_not_found", lang))

    is_participant = any(p.user_id == user.id for p in room.participants)
    if not is_participant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("chat.not_participant", lang))

    before_id = uuid.UUID(before) if before else None
    messages = await get_messages(session, room_id=room.id, before_id=before_id, limit=limit)

    return [
        MessageResponse(
            id=m.id,
            room_id=m.room_id,
            sender_id=m.sender_id,
            sender_nickname=m.sender.nickname if m.sender else None,
            type=m.type.value,
            content=m.content,
            is_deleted=m.is_deleted,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/rooms/{room_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    room_id: str,
    body: SendMessageRequest,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
):
    try:
        msg = await send_message(
            session,
            room_id=uuid.UUID(room_id),
            sender_id=user.id,
            type=body.type,
            content=body.content,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("chat.room_not_found", lang))
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("chat.not_participant", lang))
    except ValueError as e:
        if "read-only" in str(e):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("chat.room_readonly", lang))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("chat.blocked_word", lang))

    await session.commit()
    return MessageResponse(
        id=msg.id,
        room_id=msg.room_id,
        sender_id=msg.sender_id,
        sender_nickname=user.nickname,
        type=msg.type.value,
        content=msg.content,
        is_deleted=msg.is_deleted,
        created_at=msg.created_at,
    )


@router.post("/rooms/{room_id}/read")
async def mark_read(
    room_id: str,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
):
    try:
        await mark_room_read(session, room_id=uuid.UUID(room_id), user_id=user.id)
        await session.commit()
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("chat.not_participant", lang))
    return {"status": "ok"}
