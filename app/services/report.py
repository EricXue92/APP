import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.models.report import Report, ReportResolution, ReportStatus, ReportTargetType
from app.models.review import Review
from app.models.user import User


async def create_report(
    session: AsyncSession,
    *,
    reporter_id: uuid.UUID,
    reported_user_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID | None,
    reason: str,
    description: str | None = None,
    lang: str = "en",
) -> Report:
    if reporter_id == reported_user_id:
        raise ValueError(t("report.cannot_report_self", lang))

    tt = ReportTargetType(target_type)

    # Determine effective target_id
    if tt == ReportTargetType.USER:
        effective_target_id = reported_user_id
    else:
        if target_id is None:
            raise ValueError(t("report.target_not_found", lang))
        effective_target_id = target_id

    # Validate review target exists and is not already hidden
    if tt == ReportTargetType.REVIEW:
        result = await session.execute(
            select(Review).where(Review.id == effective_target_id)
        )
        review = result.scalar_one_or_none()
        if review is None:
            raise ValueError(t("report.target_not_found", lang))
        if review.is_hidden:
            raise ValueError(t("report.review_already_hidden", lang))

    # Check duplicate
    existing = await session.execute(
        select(Report).where(
            Report.reporter_id == reporter_id,
            Report.target_type == tt,
            Report.target_id == effective_target_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError(t("report.already_reported", lang))

    report = Report(
        reporter_id=reporter_id,
        reported_user_id=reported_user_id,
        target_type=tt,
        target_id=effective_target_id,
        reason=reason,
        description=description,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


async def list_my_reports(session: AsyncSession, reporter_id: uuid.UUID) -> list[Report]:
    result = await session.execute(
        select(Report).where(Report.reporter_id == reporter_id).order_by(Report.created_at.desc())
    )
    return list(result.scalars().all())


async def list_reports(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Report]:
    query = select(Report)
    if status:
        query = query.where(Report.status == ReportStatus(status))
    query = query.order_by(Report.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_report_by_id(session: AsyncSession, report_id: uuid.UUID) -> Report | None:
    result = await session.execute(select(Report).where(Report.id == report_id))
    return result.scalar_one_or_none()


async def resolve_report(
    session: AsyncSession,
    *,
    report_id: uuid.UUID,
    resolution: str,
    admin_id: uuid.UUID,
    lang: str = "en",
) -> Report:
    report = await get_report_by_id(session, report_id)
    if report is None:
        raise ValueError(t("report.not_found", lang))

    if report.status == ReportStatus.RESOLVED:
        raise ValueError(t("report.already_resolved", lang))

    res = ReportResolution(resolution)

    # content_hidden only valid for review targets
    if res == ReportResolution.CONTENT_HIDDEN and report.target_type != ReportTargetType.REVIEW:
        raise ValueError(t("report.invalid_resolution_for_target", lang))

    # Execute side effects
    if res == ReportResolution.CONTENT_HIDDEN:
        result = await session.execute(
            select(Review).where(Review.id == report.target_id)
        )
        review = result.scalar_one_or_none()
        if review:
            review.is_hidden = True

    elif res == ReportResolution.SUSPENDED:
        result = await session.execute(
            select(User).where(User.id == report.reported_user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.is_suspended = True

    report.status = ReportStatus.RESOLVED
    report.resolution = res
    report.resolved_by = admin_id
    report.resolved_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(report)
    return report
