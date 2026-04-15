import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import AdminUser, DbSession, Lang
from app.i18n import t
from app.models.admin import AdminAction
from app.schemas.report import ReportDetailResponse, ReportResolveRequest
from app.services.admin import log_admin_action
from app.services.report import get_report_by_id, list_reports, resolve_report

router = APIRouter()


@router.get("", response_model=list[ReportDetailResponse])
async def admin_list_reports(
    admin: AdminUser,
    session: DbSession,
    report_status: str | None = Query(default=None, alias="status", pattern=r"^(pending|resolved)$"),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_reports(session, status=report_status, limit=limit, offset=offset)


@router.get("/{report_id}", response_model=ReportDetailResponse)
async def admin_get_report(report_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    report = await get_report_by_id(session, uuid.UUID(report_id))
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("report.not_found", lang))
    return report


@router.patch("/{report_id}/resolve", response_model=ReportDetailResponse)
async def admin_resolve_report(
    report_id: str,
    body: ReportResolveRequest,
    admin: AdminUser,
    session: DbSession,
    lang: Lang,
):
    try:
        report = await resolve_report(
            session,
            report_id=uuid.UUID(report_id),
            resolution=body.resolution,
            admin_id=admin.id,
            lang=lang,
        )
        await log_admin_action(
            session,
            admin_id=admin.id,
            action=AdminAction.REPORT_RESOLVED,
            target_type="report",
            target_id=report.id,
        )
        await session.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return report
