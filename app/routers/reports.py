import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.schemas.report import ReportCreateRequest, ReportResponse
from app.services.report import create_report, list_my_reports

router = APIRouter()


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
