import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import AdminUser, DbSession, Lang
from app.schemas.event import EventResponse
from app.services.admin import admin_cancel_event, admin_remove_participant, list_all_events

router = APIRouter()


@router.get("", response_model=list[EventResponse])
async def admin_list_events(
    admin: AdminUser,
    session: DbSession,
    event_status: str | None = Query(default=None, alias="status", pattern=r"^(draft|open|in_progress|completed|cancelled)$"),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_all_events(session, status=event_status, limit=limit, offset=offset)


@router.patch("/{event_id}/cancel", response_model=EventResponse)
async def admin_force_cancel_event(event_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        return await admin_cancel_event(session, admin.id, uuid.UUID(event_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{event_id}/participants/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_remove_event_participant(event_id: str, user_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        await admin_remove_participant(session, admin.id, uuid.UUID(event_id), uuid.UUID(user_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
