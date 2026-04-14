import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.notification import NotificationResponse, UnreadCountResponse
from app.services.notification import get_unread_count, list_notifications, mark_all_as_read, mark_as_read

router = APIRouter()


@router.get("", response_model=list[NotificationResponse])
async def get_notifications(
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_notifications(session, user.id, limit=limit, offset=offset)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_notification_unread_count(user: CurrentUser, session: DbSession):
    count = await get_unread_count(session, user.id)
    return UnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_notification(notification_id: str, user: CurrentUser, session: DbSession):
    try:
        await mark_as_read(session, user.id, uuid.UUID(notification_id))
        await session.commit()
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")


@router.patch("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_notifications(user: CurrentUser, session: DbSession):
    await mark_all_as_read(session, user.id)
    await session.commit()
