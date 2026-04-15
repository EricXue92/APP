import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import AdminUser, DbSession, Lang
from app.schemas.booking import BookingResponse
from app.services.admin import admin_cancel_booking, list_all_bookings

router = APIRouter()


@router.get("", response_model=list[BookingResponse])
async def admin_list_bookings(
    admin: AdminUser,
    session: DbSession,
    booking_status: str | None = Query(default=None, alias="status", pattern=r"^(open|confirmed|completed|cancelled)$"),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_all_bookings(session, status=booking_status, limit=limit, offset=offset)


@router.patch("/{booking_id}/cancel", response_model=BookingResponse)
async def admin_force_cancel_booking(booking_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        return await admin_cancel_booking(session, admin.id, uuid.UUID(booking_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
