import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.matching import MatchProposal, ProposalStatus
from app.models.notification import NotificationType
from app.models.user import User
from app.services.block import is_blocked
from app.services.booking import create_booking
from app.services.notification import create_notification
from app.services.user import get_user_by_id

DAILY_PROPOSAL_CAP = 5
PROPOSAL_EXPIRY_HOURS = 48


async def create_proposal(
    session: AsyncSession,
    *,
    proposer: User,
    target_id: uuid.UUID,
    court_id: uuid.UUID,
    match_type: str = "singles",
    play_date: date,
    start_time: time,
    end_time: time,
    message: str | None = None,
    lang: str = "en",
) -> MatchProposal:
    # Cannot propose to self
    if proposer.id == target_id:
        raise ValueError("cannot_propose_self")

    # Check target exists
    target = await get_user_by_id(session, target_id)
    if target is None:
        raise ValueError("target_not_found")

    # Check block
    if await is_blocked(session, proposer.id, target_id):
        raise ValueError("blocked")

    # Check duplicate pending
    existing = await session.execute(
        select(MatchProposal).where(
            MatchProposal.proposer_id == proposer.id,
            MatchProposal.target_id == target_id,
            MatchProposal.status == ProposalStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError("duplicate_pending")

    # Check daily cap
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count_result = await session.execute(
        select(func.count(MatchProposal.id)).where(
            MatchProposal.proposer_id == proposer.id,
            MatchProposal.created_at >= today_start,
        )
    )
    if count_result.scalar_one() >= DAILY_PROPOSAL_CAP:
        raise PermissionError("daily_cap")

    proposal = MatchProposal(
        proposer_id=proposer.id,
        target_id=target_id,
        court_id=court_id,
        match_type=match_type,
        play_date=play_date,
        start_time=start_time,
        end_time=end_time,
        message=message,
    )
    session.add(proposal)

    await create_notification(
        session,
        recipient_id=target_id,
        type=NotificationType.MATCH_PROPOSAL_RECEIVED,
        actor_id=proposer.id,
        target_type="match_proposal",
        target_id=proposal.id,
    )

    await session.commit()
    return await get_proposal_by_id(session, proposal.id)


async def get_proposal_by_id(
    session: AsyncSession, proposal_id: uuid.UUID
) -> MatchProposal | None:
    result = await session.execute(
        select(MatchProposal)
        .options(
            selectinload(MatchProposal.proposer),
            selectinload(MatchProposal.target),
            selectinload(MatchProposal.court),
        )
        .where(MatchProposal.id == proposal_id)
    )
    proposal = result.scalar_one_or_none()
    if proposal and proposal.status == ProposalStatus.PENDING:
        # Lazy expiry check
        expiry_time = proposal.created_at + timedelta(hours=PROPOSAL_EXPIRY_HOURS)
        if datetime.now(timezone.utc) > expiry_time:
            proposal.status = ProposalStatus.EXPIRED
            await session.commit()
            await session.refresh(proposal)
    return proposal


async def respond_to_proposal(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    responder: User,
    new_status: str,
    lang: str = "en",
) -> MatchProposal:
    proposal = await get_proposal_by_id(session, proposal_id)
    if proposal is None:
        raise ValueError("proposal_not_found")

    if proposal.target_id != responder.id:
        raise PermissionError("not_target")

    if proposal.status != ProposalStatus.PENDING:
        raise ValueError("proposal_not_pending")

    # Check proposer is not suspended (edge case: suspended after sending)
    proposer = await get_user_by_id(session, proposal.proposer_id)
    if proposer.is_suspended and new_status == "accepted":
        proposal.status = ProposalStatus.EXPIRED
        await session.commit()
        raise ValueError("proposer_suspended")

    proposal.status = ProposalStatus(new_status)
    proposal.responded_at = datetime.now(timezone.utc)

    if new_status == "accepted":
        # Auto-create booking
        await create_booking(
            session,
            creator=proposer,
            court_id=proposal.court_id,
            match_type=proposal.match_type,
            play_date=proposal.play_date,
            start_time=proposal.start_time,
            end_time=proposal.end_time,
            min_ntrp=proposer.ntrp_level,
            max_ntrp=responder.ntrp_level,
        )
        # Find the booking just created (latest by proposer)
        result = await session.execute(
            select(Booking)
            .where(
                Booking.creator_id == proposer.id,
                Booking.play_date == proposal.play_date,
                Booking.start_time == proposal.start_time,
                Booking.court_id == proposal.court_id,
                Booking.status == BookingStatus.OPEN,
            )
            .order_by(Booking.created_at.desc())
            .limit(1)
        )
        booking = result.scalar_one_or_none()
        if booking:
            participant = BookingParticipant(
                booking_id=booking.id,
                user_id=responder.id,
                status=ParticipantStatus.ACCEPTED,
            )
            session.add(participant)

        await create_notification(
            session,
            recipient_id=proposal.proposer_id,
            type=NotificationType.MATCH_PROPOSAL_ACCEPTED,
            actor_id=responder.id,
            target_type="match_proposal",
            target_id=proposal.id,
        )
    elif new_status == "rejected":
        await create_notification(
            session,
            recipient_id=proposal.proposer_id,
            type=NotificationType.MATCH_PROPOSAL_REJECTED,
            actor_id=responder.id,
            target_type="match_proposal",
            target_id=proposal.id,
        )

    await session.commit()
    return await get_proposal_by_id(session, proposal.id)


async def list_proposals(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    direction: str | None = None,
    status_filter: str | None = None,
) -> list[MatchProposal]:
    query = select(MatchProposal).options(
        selectinload(MatchProposal.proposer),
        selectinload(MatchProposal.target),
        selectinload(MatchProposal.court),
    )

    if direction == "sent":
        query = query.where(MatchProposal.proposer_id == user_id)
    elif direction == "received":
        query = query.where(MatchProposal.target_id == user_id)
    else:
        query = query.where(
            (MatchProposal.proposer_id == user_id) | (MatchProposal.target_id == user_id)
        )

    if status_filter:
        query = query.where(MatchProposal.status == ProposalStatus(status_filter))

    query = query.order_by(MatchProposal.created_at.desc())
    result = await session.execute(query)
    proposals = list(result.scalars().all())

    # Lazy expiry check for pending proposals
    now = datetime.now(timezone.utc)
    for p in proposals:
        if p.status == ProposalStatus.PENDING:
            expiry_time = p.created_at + timedelta(hours=PROPOSAL_EXPIRY_HOURS)
            if now > expiry_time:
                p.status = ProposalStatus.EXPIRED

    if any(p.status == ProposalStatus.EXPIRED for p in proposals):
        await session.commit()

    return proposals


async def expire_proposals_on_block(
    session: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> None:
    """Expire any pending proposals between two users when a block occurs."""
    result = await session.execute(
        select(MatchProposal).where(
            MatchProposal.status == ProposalStatus.PENDING,
            (
                (MatchProposal.proposer_id == user_a) & (MatchProposal.target_id == user_b)
                | (MatchProposal.proposer_id == user_b) & (MatchProposal.target_id == user_a)
            ),
        )
    )
    for proposal in result.scalars().all():
        proposal.status = ProposalStatus.EXPIRED
    await session.flush()
