import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.booking_invite import BookingInviteCreateRequest, BookingInviteResponse
from app.services.booking_invite import (
    accept_invite,
    create_invite,
    get_invite_by_id,
    list_received_invites,
    list_sent_invites,
    reject_invite,
)
from app.services.court import get_court_by_id

router = APIRouter()


def _to_response(invite) -> BookingInviteResponse:
    return BookingInviteResponse(
        id=invite.id,
        inviter_id=invite.inviter_id,
        invitee_id=invite.invitee_id,
        court_id=invite.court_id,
        match_type=invite.match_type.value,
        play_date=invite.play_date,
        start_time=invite.start_time,
        end_time=invite.end_time,
        gender_requirement=invite.gender_requirement.value if hasattr(invite.gender_requirement, 'value') else invite.gender_requirement,
        cost_per_person=invite.cost_per_person,
        description=invite.description,
        status=invite.status.value,
        booking_id=invite.booking_id,
        created_at=invite.created_at,
    )


@router.post("", response_model=BookingInviteResponse, status_code=status.HTTP_201_CREATED)
async def create_booking_invite(
    body: BookingInviteCreateRequest, user: CurrentUser, session: DbSession, lang: Lang
):
    if user.credit_score < 60:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("booking.credit_too_low", lang))

    court = await get_court_by_id(session, body.court_id)
    if court is None or not court.is_approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("court.not_found", lang))

    if body.play_date < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("booking.play_date_past", lang))

    try:
        invite = await create_invite(
            session,
            inviter=user,
            invitee_id=body.invitee_id,
            court_id=body.court_id,
            match_type=body.match_type,
            play_date=body.play_date,
            start_time=body.start_time,
            end_time=body.end_time,
            gender_requirement=body.gender_requirement,
            cost_per_person=body.cost_per_person,
            description=body.description,
        )
    except ValueError as e:
        msg = str(e)
        if msg == "cannot_invite_self":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("invite.cannot_invite_self", lang))
        if msg == "invitee_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("invite.invitee_not_found", lang))
        if msg == "blocked":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("block.user_blocked", lang))
        raise
    except LookupError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("invite.duplicate_pending", lang))

    return _to_response(invite)


@router.get("/sent", response_model=list[BookingInviteResponse])
async def get_sent_invites(user: CurrentUser, session: DbSession):
    invites = await list_sent_invites(session, user.id)
    return [_to_response(inv) for inv in invites]


@router.get("/received", response_model=list[BookingInviteResponse])
async def get_received_invites(user: CurrentUser, session: DbSession):
    invites = await list_received_invites(session, user.id)
    return [_to_response(inv) for inv in invites]


@router.get("/{invite_id}", response_model=BookingInviteResponse)
async def get_invite(invite_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    invite = await get_invite_by_id(session, uuid.UUID(invite_id))
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("invite.not_found", lang))
    if invite.inviter_id != user.id and invite.invitee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("invite.not_participant", lang))
    return _to_response(invite)


@router.post("/{invite_id}/accept", response_model=BookingInviteResponse)
async def accept_booking_invite(invite_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        invite = await accept_invite(session, invite_id=uuid.UUID(invite_id), invitee=user)
    except ValueError as e:
        msg = str(e)
        if msg == "invite_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("invite.not_found", lang))
        if msg == "invite_not_pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("invite.not_pending", lang))
        raise
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("invite.not_invitee", lang))
    return _to_response(invite)


@router.post("/{invite_id}/reject", response_model=BookingInviteResponse)
async def reject_booking_invite(invite_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        invite = await reject_invite(session, invite_id=uuid.UUID(invite_id), invitee=user)
    except ValueError as e:
        msg = str(e)
        if msg == "invite_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("invite.not_found", lang))
        if msg == "invite_not_pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("invite.not_pending", lang))
        raise
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("invite.not_invitee", lang))
    return _to_response(invite)
