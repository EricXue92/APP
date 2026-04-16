import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import BookingParticipant, BookingStatus, MatchType, ParticipantStatus
from app.models.booking_invite import BookingInvite, InviteStatus
from app.models.court import Court
from app.models.notification import NotificationType
from app.models.user import User
from app.services.block import is_blocked
from app.services.booking import create_booking
from app.services.chat import create_chat_room
from app.services.notification import create_notification
from app.services.user import get_user_by_id


async def _load_invite(session: AsyncSession, invite_id: uuid.UUID) -> BookingInvite | None:
    result = await session.execute(
        select(BookingInvite)
        .options(
            selectinload(BookingInvite.inviter),
            selectinload(BookingInvite.invitee),
            selectinload(BookingInvite.court),
        )
        .where(BookingInvite.id == invite_id)
    )
    return result.scalar_one_or_none()


def _check_expired(invite: BookingInvite) -> bool:
    """Mark invite as expired if play_date has passed. Returns True if expired."""
    if invite.status == InviteStatus.PENDING and invite.play_date < date.today():
        invite.status = InviteStatus.EXPIRED
        return True
    return False


async def create_invite(
    session: AsyncSession,
    *,
    inviter: User,
    invitee_id: uuid.UUID,
    court_id: uuid.UUID,
    match_type: str,
    play_date: date,
    start_time: datetime.time,
    end_time: datetime.time,
    gender_requirement: str = "any",
    cost_per_person: int | None = None,
    description: str | None = None,
) -> BookingInvite:
    # Cannot invite self
    if inviter.id == invitee_id:
        raise ValueError("cannot_invite_self")

    # Check invitee exists
    invitee = await get_user_by_id(session, invitee_id)
    if invitee is None:
        raise ValueError("invitee_not_found")

    # Check block
    if await is_blocked(session, inviter.id, invitee_id):
        raise ValueError("blocked")

    # Check duplicate pending
    existing = await session.execute(
        select(BookingInvite).where(
            BookingInvite.inviter_id == inviter.id,
            BookingInvite.invitee_id == invitee_id,
            BookingInvite.status == InviteStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError("duplicate_pending")

    invite = BookingInvite(
        inviter_id=inviter.id,
        invitee_id=invitee_id,
        court_id=court_id,
        match_type=MatchType(match_type),
        play_date=play_date,
        start_time=start_time,
        end_time=end_time,
        gender_requirement=gender_requirement,
        cost_per_person=cost_per_person,
        description=description,
    )
    session.add(invite)

    await create_notification(
        session,
        recipient_id=invitee_id,
        type=NotificationType.BOOKING_INVITE_RECEIVED,
        actor_id=inviter.id,
        target_type="booking_invite",
        target_id=invite.id,
    )

    await session.commit()
    return await _load_invite(session, invite.id)


async def accept_invite(
    session: AsyncSession,
    *,
    invite_id: uuid.UUID,
    invitee: User,
) -> BookingInvite:
    invite = await _load_invite(session, invite_id)
    if invite is None:
        raise ValueError("invite_not_found")

    if invite.invitee_id != invitee.id:
        raise PermissionError("not_invitee")

    _check_expired(invite)
    if invite.status != InviteStatus.PENDING:
        raise ValueError("invite_not_pending")

    invite.status = InviteStatus.ACCEPTED

    inviter = await get_user_by_id(session, invite.inviter_id)

    # Determine NTRP range from both players (for record-keeping)
    from app.services.booking import _ntrp_to_float
    inviter_ntrp = _ntrp_to_float(inviter.ntrp_level)
    invitee_ntrp = _ntrp_to_float(invitee.ntrp_level)
    min_ntrp = inviter.ntrp_level if inviter_ntrp <= invitee_ntrp else invitee.ntrp_level
    max_ntrp = invitee.ntrp_level if invitee_ntrp >= inviter_ntrp else inviter.ntrp_level

    # Create booking (inviter as creator)
    booking = await create_booking(
        session,
        creator=inviter,
        court_id=invite.court_id,
        match_type=invite.match_type.value,
        play_date=invite.play_date,
        start_time=invite.start_time,
        end_time=invite.end_time,
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_requirement=invite.gender_requirement.value if hasattr(invite.gender_requirement, 'value') else invite.gender_requirement,
        cost_per_person=invite.cost_per_person,
        description=invite.description,
    )

    # Add invitee as accepted participant
    participant = BookingParticipant(
        booking_id=booking.id,
        user_id=invitee.id,
        status=ParticipantStatus.ACCEPTED,
    )
    session.add(participant)
    await session.flush()

    # Set booking to confirmed
    booking.status = BookingStatus.CONFIRMED
    await session.flush()

    # Create chat room
    court = invite.court or await session.get(Court, invite.court_id)
    court_name = court.name if court else ""
    await create_chat_room(
        session,
        booking=booking,
        participant_ids=[inviter.id, invitee.id],
        court_name=court_name,
    )

    invite.booking_id = booking.id

    await create_notification(
        session,
        recipient_id=invite.inviter_id,
        type=NotificationType.BOOKING_INVITE_ACCEPTED,
        actor_id=invitee.id,
        target_type="booking_invite",
        target_id=invite.id,
    )

    await session.commit()
    return await _load_invite(session, invite.id)


async def reject_invite(
    session: AsyncSession,
    *,
    invite_id: uuid.UUID,
    invitee: User,
) -> BookingInvite:
    invite = await _load_invite(session, invite_id)
    if invite is None:
        raise ValueError("invite_not_found")

    if invite.invitee_id != invitee.id:
        raise PermissionError("not_invitee")

    _check_expired(invite)
    if invite.status != InviteStatus.PENDING:
        raise ValueError("invite_not_pending")

    invite.status = InviteStatus.REJECTED

    await create_notification(
        session,
        recipient_id=invite.inviter_id,
        type=NotificationType.BOOKING_INVITE_REJECTED,
        actor_id=invitee.id,
        target_type="booking_invite",
        target_id=invite.id,
    )

    await session.commit()
    return await _load_invite(session, invite.id)


async def get_invite_by_id(session: AsyncSession, invite_id: uuid.UUID) -> BookingInvite | None:
    invite = await _load_invite(session, invite_id)
    if invite and _check_expired(invite):
        await session.commit()
    return invite


async def list_sent_invites(session: AsyncSession, user_id: uuid.UUID) -> list[BookingInvite]:
    result = await session.execute(
        select(BookingInvite)
        .options(
            selectinload(BookingInvite.inviter),
            selectinload(BookingInvite.invitee),
            selectinload(BookingInvite.court),
        )
        .where(BookingInvite.inviter_id == user_id)
        .order_by(BookingInvite.created_at.desc())
    )
    return list(result.scalars().all())


async def list_received_invites(session: AsyncSession, user_id: uuid.UUID) -> list[BookingInvite]:
    result = await session.execute(
        select(BookingInvite)
        .options(
            selectinload(BookingInvite.inviter),
            selectinload(BookingInvite.invitee),
            selectinload(BookingInvite.court),
        )
        .where(BookingInvite.invitee_id == user_id)
        .order_by(BookingInvite.created_at.desc())
    )
    invites = list(result.scalars().all())

    # Lazy expiry for pending invites
    expired_any = False
    for inv in invites:
        if _check_expired(inv):
            expired_any = True
    if expired_any:
        await session.commit()

    return invites
