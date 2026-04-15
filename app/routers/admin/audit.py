import uuid

from fastapi import APIRouter, Query

from app.dependencies import AdminUser, DbSession
from app.schemas.admin import AuditLogEntry
from app.services.admin import list_audit_logs

router = APIRouter()


@router.get("", response_model=list[AuditLogEntry])
async def admin_list_audit_logs(
    admin: AdminUser,
    session: DbSession,
    action: str | None = Query(default=None),
    admin_id: uuid.UUID | None = Query(default=None),
    target_type: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_audit_logs(session, action=action, admin_id=admin_id, target_type=target_type, limit=limit, offset=offset)
