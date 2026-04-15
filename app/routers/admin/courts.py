import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import AdminUser, DbSession, Lang, SuperAdminUser
from app.schemas.admin import CourtAdminResponse
from app.services.admin import approve_court, delete_court, list_all_courts, reject_court

router = APIRouter()


@router.get("", response_model=list[CourtAdminResponse])
async def admin_list_courts(
    admin: AdminUser,
    session: DbSession,
    is_approved: bool | None = Query(default=None),
    city: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_all_courts(session, is_approved=is_approved, city=city, limit=limit, offset=offset)


@router.patch("/{court_id}/approve", response_model=CourtAdminResponse)
async def admin_approve_court(court_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        return await approve_court(session, admin.id, uuid.UUID(court_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{court_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def admin_reject_court(court_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        await reject_court(session, admin.id, uuid.UUID(court_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{court_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_court(court_id: str, admin: SuperAdminUser, session: DbSession, lang: Lang):
    try:
        await delete_court(session, admin.id, uuid.UUID(court_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
