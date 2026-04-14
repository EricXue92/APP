import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import AdminUser, CurrentUser, DbSession, Lang
from app.schemas.report import ReportCreateRequest, ReportDetailResponse, ReportResolveRequest, ReportResponse
from app.services.report import create_report, get_report_by_id, list_my_reports, list_reports, resolve_report

router = APIRouter()
admin_router = APIRouter()


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def submit_report(body: ReportCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        report = await create_report(
            session,
            reporter_id=user.id,
            reported_user_id=body.reported_user_id,
            target_type=body.target_type,
            target_id=body.target_id,
            reason=body.reason,
            description=body.description,
            lang=lang,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return report


@router.get("/mine", response_model=list[ReportResponse])
async def get_my_reports(user: CurrentUser, session: DbSession):
    return await list_my_reports(session, user.id)


# --- Admin Endpoints ---


@admin_router.get("", response_model=list[ReportDetailResponse])
async def admin_list_reports(
    admin: AdminUser,
    session: DbSession,
    report_status: str | None = Query(default=None, alias="status", pattern=r"^(pending|resolved)$"),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_reports(session, status=report_status, limit=limit, offset=offset)


@admin_router.get("/{report_id}", response_model=ReportDetailResponse)
async def admin_get_report(report_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    report = await get_report_by_id(session, uuid.UUID(report_id))
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@admin_router.patch("/{report_id}/resolve", response_model=ReportDetailResponse)
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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return report
