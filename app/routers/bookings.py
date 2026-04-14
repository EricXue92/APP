import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.models.booking import BookingStatus, ParticipantStatus
from app.models.user import Gender
from app.schemas.booking import (
    BookingCreateRequest,
    BookingDetailResponse,
    BookingResponse,
    ParticipantResponse,
    ParticipantUpdateRequest,
)
from app.services.booking import (
    cancel_booking,
    complete_booking,
    confirm_booking,
    count_accepted_participants,
    create_booking,
    get_booking_by_id,
    join_booking,
    list_bookings,
    list_my_bookings,
    update_participant_status,
    _ntrp_to_float,
)
from app.services.block import is_blocked
from app.services.court import get_court_by_id

router = APIRouter()


def _booking_to_detail(booking) -> dict:
    """Convert a Booking ORM object to BookingDetailResponse-compatible dict."""
    participants = [
        ParticipantResponse(
            id=p.id,
            user_id=p.user_id,
            nickname=p.user.nickname,
            status=p.status.value,
            joined_at=p.joined_at,
        )
        for p in booking.participants
    ]
    return BookingDetailResponse(
        id=booking.id,
        creator_id=booking.creator_id,
        court_id=booking.court_id,
        match_type=booking.match_type.value,
        play_date=booking.play_date,
        start_time=booking.start_time,
        end_time=booking.end_time,
        min_ntrp=booking.min_ntrp,
        max_ntrp=booking.max_ntrp,
        gender_requirement=booking.gender_requirement.value,
        max_participants=booking.max_participants,
        cost_per_person=booking.cost_per_person,
        description=booking.description,
        status=booking.status.value,
        created_at=booking.created_at,
        participants=participants,
        court_name=booking.court.name,
    )


@router.post("", response_model=BookingDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_new_booking(body: BookingCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    if user.credit_score < 60:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.credit_too_low", lang))

    court = await get_court_by_id(session, body.court_id)
    if court is None or not court.is_approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("court.not_found", lang))

    if body.play_date < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.play_date_past", lang))

    booking = await create_booking(
        session,
        creator=user,
        court_id=body.court_id,
        match_type=body.match_type,
        play_date=body.play_date,
        start_time=body.start_time,
        end_time=body.end_time,
        min_ntrp=body.min_ntrp,
        max_ntrp=body.max_ntrp,
        gender_requirement=body.gender_requirement,
        cost_per_person=body.cost_per_person,
        description=body.description,
    )
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.get("", response_model=list[BookingResponse])
async def get_bookings(
    session: DbSession,
    user: CurrentUser,
    city: str | None = Query(default=None),
    match_type: str | None = Query(default=None, pattern=r"^(singles|doubles)$"),
    gender_requirement: str | None = Query(default=None, pattern=r"^(male_only|female_only|any)$"),
):
    bookings = await list_bookings(
        session, city=city, match_type=match_type, gender_requirement=gender_requirement,
        current_user_id=user.id,
    )
    return bookings


@router.get("/my", response_model=list[BookingResponse])
async def get_my_bookings(
    user: CurrentUser,
    session: DbSession,
    booking_status: str | None = Query(default=None, alias="status", pattern=r"^(open|confirmed|completed|cancelled)$"),
):
    bookings = await list_my_bookings(session, user.id, status=booking_status)
    return bookings


@router.get("/{booking_id}", response_model=BookingDetailResponse)
async def get_booking(booking_id: str, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))
    return _booking_to_detail(booking)


@router.post("/{booking_id}/join", response_model=BookingDetailResponse)
async def join_existing_booking(booking_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.status != BookingStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.not_open", lang))

    # Check if already joined
    for p in booking.participants:
        if p.user_id == user.id and p.status != ParticipantStatus.CANCELLED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("booking.already_joined", lang))

    # Check NTRP range
    user_ntrp = _ntrp_to_float(user.ntrp_level)
    min_ntrp = _ntrp_to_float(booking.min_ntrp)
    max_ntrp = _ntrp_to_float(booking.max_ntrp)
    if user_ntrp < min_ntrp or user_ntrp > max_ntrp:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.ntrp_out_of_range", lang))

    # Check gender requirement
    if booking.gender_requirement.value == "male_only" and user.gender != Gender.MALE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.gender_mismatch", lang))
    if booking.gender_requirement.value == "female_only" and user.gender != Gender.FEMALE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.gender_mismatch", lang))

    # Check block relationship
    if await is_blocked(session, user.id, booking.creator_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("block.user_blocked", lang))

    # Check if full
    accepted_count = count_accepted_participants(booking)
    if accepted_count >= booking.max_participants:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("booking.full", lang))

    await join_booking(session, booking, user)
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.post("/{booking_id}/confirm", response_model=BookingDetailResponse)
async def confirm_existing_booking(booking_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.not_creator", lang))

    if booking.status != BookingStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.not_open", lang))

    if count_accepted_participants(booking) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.not_enough_participants", lang))

    booking = await confirm_booking(session, booking)
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.post("/{booking_id}/cancel", response_model=BookingDetailResponse)
async def cancel_existing_booking(booking_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.already_cancelled", lang))

    if booking.status == BookingStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.cannot_complete", lang))

    booking = await cancel_booking(session, booking, user)
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.post("/{booking_id}/complete", response_model=BookingDetailResponse)
async def complete_existing_booking(booking_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.not_creator", lang))

    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.cannot_complete", lang))

    play_dt = datetime.combine(booking.play_date, booking.start_time, tzinfo=timezone.utc)
    if datetime.now(timezone.utc) < play_dt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.cannot_complete", lang))

    booking = await complete_booking(session, booking)
    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)


@router.patch("/{booking_id}/participants/{user_id}", response_model=BookingDetailResponse)
async def manage_participant(
    booking_id: str,
    user_id: str,
    body: ParticipantUpdateRequest,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
):
    booking = await get_booking_by_id(session, uuid.UUID(booking_id))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("booking.not_found", lang))

    if booking.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.not_creator", lang))

    participant = await update_participant_status(session, booking, uuid.UUID(user_id), body.status)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("common.not_found", lang))

    booking = await get_booking_by_id(session, booking.id)
    return _booking_to_detail(booking)
