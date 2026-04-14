import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.court import CourtCreateRequest, CourtResponse
from app.services.court import create_court, get_court_by_id, list_courts

router = APIRouter()


@router.get("", response_model=list[CourtResponse])
async def get_courts(
    session: DbSession,
    city: str | None = Query(default=None),
    court_type: str | None = Query(default=None, pattern=r"^(indoor|outdoor)$"),
):
    courts = await list_courts(session, city=city, court_type=court_type)
    return courts


@router.get("/{court_id}", response_model=CourtResponse)
async def get_court(court_id: str, session: DbSession, lang: Lang):
    court = await get_court_by_id(session, uuid.UUID(court_id))
    if court is None or not court.is_approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("court.not_found", lang))
    return court


@router.post("", response_model=CourtResponse, status_code=status.HTTP_201_CREATED)
async def submit_court(body: CourtCreateRequest, user: CurrentUser, session: DbSession):
    court = await create_court(
        session,
        name=body.name,
        address=body.address,
        city=body.city,
        latitude=body.latitude,
        longitude=body.longitude,
        court_type=body.court_type,
        surface_type=body.surface_type,
        created_by=user.id,
        is_approved=False,
    )
    return court
