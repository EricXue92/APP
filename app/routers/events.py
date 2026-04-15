import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.models.event import EventStatus, EventParticipantStatus
from app.schemas.event import (
    EventCreateRequest,
    EventDetailResponse,
    EventMatchResponse,
    EventParticipantResponse,
    EventResponse,
    EventUpdateRequest,
    ScoreSubmitRequest,
    StandingsEntry,
)
from app.services.event import (
    create_event,
    get_event_by_id,
    list_events,
    list_my_events,
    update_event,
)

router = APIRouter()


def _participant_response(p) -> EventParticipantResponse:
    return EventParticipantResponse(
        id=p.id,
        user_id=p.user_id,
        nickname=p.user.nickname,
        ntrp_level=p.user.ntrp_level,
        seed=p.seed,
        group_name=p.group_name,
        team_name=p.team_name,
        status=p.status.value,
        joined_at=p.joined_at,
    )


def _event_to_response(event, include_participants: bool = False) -> dict:
    participant_count = len(event.participants) if event.participants else 0
    data = EventResponse(
        id=event.id,
        creator_id=event.creator_id,
        name=event.name,
        event_type=event.event_type.value,
        min_ntrp=event.min_ntrp,
        max_ntrp=event.max_ntrp,
        gender_requirement=event.gender_requirement,
        max_participants=event.max_participants,
        games_per_set=event.games_per_set,
        num_sets=event.num_sets,
        match_tiebreak=event.match_tiebreak,
        start_date=event.start_date,
        end_date=event.end_date,
        registration_deadline=event.registration_deadline,
        entry_fee=event.entry_fee,
        description=event.description,
        status=event.status.value,
        participant_count=participant_count,
        created_at=event.created_at,
    )
    if include_participants:
        participants = [_participant_response(p) for p in event.participants]
        return EventDetailResponse(**data.model_dump(), participants=participants)
    return data


@router.post("", response_model=EventDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_new_event(body: EventCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    if user.credit_score < 80:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("event.credit_too_low", lang))

    event = await create_event(
        session,
        creator=user,
        name=body.name,
        event_type=body.event_type,
        min_ntrp=body.min_ntrp,
        max_ntrp=body.max_ntrp,
        gender_requirement=body.gender_requirement,
        max_participants=body.max_participants,
        games_per_set=body.games_per_set,
        num_sets=body.num_sets,
        match_tiebreak=body.match_tiebreak,
        start_date=body.start_date,
        end_date=body.end_date,
        registration_deadline=body.registration_deadline,
        entry_fee=body.entry_fee,
        description=body.description,
    )
    event = await get_event_by_id(session, event.id)
    return _event_to_response(event, include_participants=True)


@router.get("", response_model=list[EventResponse])
async def get_events(
    session: DbSession,
    user: CurrentUser,
    event_status: str | None = Query(default=None, alias="status", pattern=r"^(draft|open|in_progress|completed|cancelled)$"),
    event_type: str | None = Query(default=None, pattern=r"^(singles_elimination|doubles_elimination|round_robin)$"),
):
    events = await list_events(session, status=event_status, event_type=event_type, current_user_id=user.id)
    return [_event_to_response(e) for e in events]


@router.get("/my", response_model=list[EventResponse])
async def get_my_events(user: CurrentUser, session: DbSession):
    events = await list_my_events(session, user.id)
    return [_event_to_response(e) for e in events]


@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(event_id: str, session: DbSession, user: CurrentUser, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    return _event_to_response(event, include_participants=True)


@router.patch("/{event_id}", response_model=EventDetailResponse)
async def update_existing_event(event_id: str, body: EventUpdateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    event = await get_event_by_id(session, uuid.UUID(event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("event.not_found", lang))
    if event.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("event.not_creator", lang))
    if event.status not in (EventStatus.DRAFT, EventStatus.OPEN):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("event.cannot_modify", lang))

    updates = body.model_dump(exclude_unset=True)
    event = await update_event(session, event, **updates)
    event = await get_event_by_id(session, event.id)
    return _event_to_response(event, include_participants=True)
