from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.matching import (
    BookingRecommendationResponse,
    CandidateResponse,
    PreferenceCreateRequest,
    PreferenceResponse,
    TimeSlotResponse,
    ToggleResponse,
)
from app.services.matching import (
    create_preference,
    get_preference_by_user,
    search_booking_recommendations,
    search_candidates,
    toggle_preference,
    update_preference,
)

router = APIRouter()


def _pref_to_response(pref) -> PreferenceResponse:
    return PreferenceResponse(
        id=pref.id,
        user_id=pref.user_id,
        match_type=pref.match_type.value,
        min_ntrp=pref.min_ntrp,
        max_ntrp=pref.max_ntrp,
        gender_preference=pref.gender_preference.value,
        max_distance_km=pref.max_distance_km,
        is_active=pref.is_active,
        last_active_at=pref.last_active_at,
        time_slots=[
            TimeSlotResponse(
                id=ts.id,
                day_of_week=ts.day_of_week,
                start_time=ts.start_time,
                end_time=ts.end_time,
            )
            for ts in pref.time_slots
        ],
        court_ids=[pc.court_id for pc in pref.preferred_courts],
        created_at=pref.created_at,
        updated_at=pref.updated_at,
    )


@router.post("/preferences", response_model=PreferenceResponse, status_code=status.HTTP_201_CREATED)
async def create_match_preference(body: PreferenceCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        pref = await create_preference(
            session,
            user_id=user.id,
            match_type=body.match_type,
            min_ntrp=body.min_ntrp,
            max_ntrp=body.max_ntrp,
            gender_preference=body.gender_preference,
            max_distance_km=body.max_distance_km,
            time_slots=[s.model_dump() for s in body.time_slots],
            court_ids=body.court_ids,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("matching.preference_exists", lang))
    return _pref_to_response(pref)


@router.get("/preferences", response_model=PreferenceResponse)
async def get_match_preference(user: CurrentUser, session: DbSession, lang: Lang):
    pref = await get_preference_by_user(session, user.id)
    if pref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    return _pref_to_response(pref)


@router.put("/preferences", response_model=PreferenceResponse)
async def update_match_preference(body: PreferenceCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        pref = await update_preference(
            session,
            user_id=user.id,
            match_type=body.match_type,
            min_ntrp=body.min_ntrp,
            max_ntrp=body.max_ntrp,
            gender_preference=body.gender_preference,
            max_distance_km=body.max_distance_km,
            time_slots=[s.model_dump() for s in body.time_slots],
            court_ids=body.court_ids,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    return _pref_to_response(pref)


@router.patch("/preferences/toggle", response_model=ToggleResponse)
async def toggle_match_preference(user: CurrentUser, session: DbSession, lang: Lang):
    try:
        pref = await toggle_preference(session, user.id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    return ToggleResponse(is_active=pref.is_active)


@router.get("/candidates", response_model=list[CandidateResponse])
async def find_candidates(user: CurrentUser, session: DbSession, lang: Lang):
    pref = await get_preference_by_user(session, user.id)
    if pref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    if not pref.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("matching.preference_inactive", lang))

    candidates = await search_candidates(session, user, pref)
    return candidates


@router.get("/bookings", response_model=list[BookingRecommendationResponse])
async def find_booking_recommendations(user: CurrentUser, session: DbSession, lang: Lang):
    pref = await get_preference_by_user(session, user.id)
    if pref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("matching.preference_not_found", lang))
    if not pref.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("matching.preference_inactive", lang))

    bookings = await search_booking_recommendations(session, user, pref)
    return bookings
