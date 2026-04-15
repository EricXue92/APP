import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import AdminUser, DbSession, Lang, SuperAdminUser
from app.schemas.admin import AdminUserDetailResponse, AdminUserListResponse, UserRoleUpdateRequest
from app.services.admin import (
    change_user_role,
    get_user_detail,
    list_users,
    reset_user_credit,
    suspend_user,
    unsuspend_user,
)

router = APIRouter()


@router.get("", response_model=list[AdminUserListResponse])
async def admin_list_users(
    admin: AdminUser,
    session: DbSession,
    role: str | None = Query(default=None, pattern=r"^(user|admin|superadmin)$"),
    city: str | None = Query(default=None),
    is_suspended: bool | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_users(session, role=role, city=city, is_suspended=is_suspended, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=AdminUserDetailResponse)
async def admin_get_user(user_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        return await get_user_detail(session, uuid.UUID(user_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{user_id}/suspend", response_model=AdminUserListResponse)
async def admin_suspend_user(user_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        return await suspend_user(session, admin.id, uuid.UUID(user_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{user_id}/unsuspend", response_model=AdminUserListResponse)
async def admin_unsuspend_user(user_id: str, admin: SuperAdminUser, session: DbSession, lang: Lang):
    try:
        return await unsuspend_user(session, admin.id, uuid.UUID(user_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{user_id}/role", response_model=AdminUserListResponse)
async def admin_change_role(user_id: str, body: UserRoleUpdateRequest, admin: SuperAdminUser, session: DbSession, lang: Lang):
    try:
        return await change_user_role(session, admin.id, uuid.UUID(user_id), body.role, lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{user_id}/reset-credit", response_model=AdminUserListResponse)
async def admin_reset_credit(user_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        return await reset_user_credit(session, admin.id, uuid.UUID(user_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
