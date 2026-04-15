import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.database import async_session
from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.chat import MessageResponse, RoomResponse, ParticipantInfo, SendMessageRequest
from app.services.auth import decode_token
from app.services.chat import (
    get_messages,
    get_room_by_id,
    manager,
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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=4001)
        return

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=4001)
        return

    user_id_str = payload.get("sub")
    if not user_id_str:
        await websocket.close(code=4001)
        return

    user_id = uuid.UUID(user_id_str)

    await websocket.accept()
    await manager.connect(user_id, websocket)

    # Load user for validation and nickname
    async with async_session() as session:
        from app.services.user import get_user_by_id
        user = await get_user_by_id(session, user_id)
        if not user or not user.is_active or user.is_suspended:
            await websocket.close(code=4003)
            return
        user_nickname = user.nickname

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                await websocket.close(code=4002)
                break

            if raw == "ping":
                await websocket.send_text("pong")
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "data": {"code": "invalid_json", "message": "Invalid JSON"}})
                continue

            action = data.get("action")
            if action == "send":
                room_id_str = data.get("room_id")
                msg_type = data.get("type", "text")
                content = data.get("content", "")

                if not room_id_str or not content:
                    await websocket.send_json({"event": "error", "data": {"code": "missing_fields", "message": "room_id and content required"}})
                    continue

                async with async_session() as session:
                    try:
                        msg = await send_message(
                            session,
                            room_id=uuid.UUID(room_id_str),
                            sender_id=user_id,
                            type=msg_type,
                            content=content,
                        )
                        await session.commit()

                        # Get participant IDs for broadcast
                        room = await get_room_by_id(session, msg.room_id)
                        participant_ids = [p.user_id for p in room.participants]

                        msg_payload = {
                            "event": "new_message",
                            "data": {
                                "id": str(msg.id),
                                "room_id": str(msg.room_id),
                                "sender_id": str(msg.sender_id),
                                "sender_nickname": user_nickname,
                                "type": msg.type.value,
                                "content": msg.content,
                                "created_at": msg.created_at.isoformat(),
                            },
                        }

                        # Broadcast to others
                        await manager.broadcast_to_room(participant_ids, msg_payload, exclude=user_id)

                        # Ack to sender
                        await websocket.send_json({
                            "event": "ack",
                            "data": {"id": str(msg.id), "created_at": msg.created_at.isoformat()},
                        })

                    except ValueError as e:
                        error_code = "room_readonly" if "read-only" in str(e) else "blocked_word"
                        await websocket.send_json({"event": "error", "data": {"code": error_code, "message": str(e)}})
                    except PermissionError:
                        await websocket.send_json({"event": "error", "data": {"code": "not_participant", "message": "Not a participant"}})
                    except LookupError:
                        await websocket.send_json({"event": "error", "data": {"code": "room_not_found", "message": "Room not found"}})
            else:
                await websocket.send_json({"event": "error", "data": {"code": "unknown_action", "message": f"Unknown action: {action}"}})

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id)
