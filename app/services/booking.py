import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.block import Block
from app.models.booking import (
    Booking,
    BookingParticipant,
    BookingStatus,
    GenderRequirement,
    MatchType,
    ParticipantStatus,
)
from app.models.court import Court
from app.models.credit import CreditReason
from app.models.notification import NotificationType
from app.models.user import Gender, User
from app.services.credit import apply_credit_change
from app.services.notification import create_notification
from app.services.chat import create_chat_room
from app.services.weather import check_free_cancel


def _ntrp_to_float(level: str) -> float:
    """Convert NTRP string like '3.5', '3.5+', '4.0-' to a float for comparison."""
    base = level.rstrip("+-")
    value = float(base)
    if level.endswith("+"):
        value += 0.05
    elif level.endswith("-"):
        value -= 0.05
    return value


def _get_cancel_reason(play_datetime: datetime) -> CreditReason:
    """Determine credit penalty tier based on time remaining until play."""
    now = datetime.now(timezone.utc)
    hours_until_play = (play_datetime - now).total_seconds() / 3600

    if hours_until_play >= 24:
        return CreditReason.CANCEL_24H
    elif hours_until_play >= 12:
        return CreditReason.CANCEL_12_24H
    else:
        return CreditReason.CANCEL_2H


async def create_booking(
    session: AsyncSession,
    *,
    creator: User,
    court_id: uuid.UUID,
    match_type: str,
    play_date: date,
    start_time: time,
    end_time: time,
    min_ntrp: str,
    max_ntrp: str,
    gender_requirement: str = "any",
    cost_per_person: int | None = None,
    description: str | None = None,
) -> Booking:
    max_participants = 2 if match_type == "singles" else 4

    booking = Booking(
        creator_id=creator.id,
        court_id=court_id,
        match_type=MatchType(match_type),
        play_date=play_date,
        start_time=start_time,
        end_time=end_time,
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_requirement=GenderRequirement(gender_requirement),
        max_participants=max_participants,
        cost_per_person=cost_per_person,
        description=description,
    )
    session.add(booking)
    await session.flush()

    participant = BookingParticipant(
        booking_id=booking.id,
        user_id=creator.id,
        status=ParticipantStatus.ACCEPTED,
    )
    session.add(participant)
    await session.commit()
    await session.refresh(booking)
    return booking


async def get_booking_by_id(session: AsyncSession, booking_id: uuid.UUID) -> Booking | None:
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.participants).selectinload(BookingParticipant.user),
            selectinload(Booking.court),
        )
        .where(Booking.id == booking_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def list_bookings(
    session: AsyncSession,
    *,
    city: str | None = None,
    match_type: str | None = None,
    gender_requirement: str | None = None,
    current_user_id: uuid.UUID | None = None,
) -> list[Booking]:
    query = (
        select(Booking)
        .join(Booking.court)
        .join(User, Booking.creator_id == User.id)
        .where(Booking.status == BookingStatus.OPEN)
    )
    if city:
        query = query.where(Court.city == city)
    if match_type:
        query = query.where(Booking.match_type == MatchType(match_type))
    if gender_requirement:
        query = query.where(Booking.gender_requirement == GenderRequirement(gender_requirement))
    if current_user_id:
        blocked_ids = (
            select(Block.blocked_id)
            .where(Block.blocker_id == current_user_id)
        )
        blocker_ids = (
            select(Block.blocker_id)
            .where(Block.blocked_id == current_user_id)
        )
        query = query.where(
            Booking.creator_id.notin_(blocked_ids),
            Booking.creator_id.notin_(blocker_ids),
        )
    query = query.order_by(User.is_ideal_player.desc(), Booking.play_date, Booking.start_time)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_my_bookings(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
) -> list[Booking]:
    query = (
        select(Booking)
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(BookingParticipant.user_id == user_id)
    )
    if status:
        query = query.where(Booking.status == BookingStatus(status))
    query = query.order_by(Booking.play_date.desc(), Booking.start_time.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def join_booking(session: AsyncSession, booking: Booking, user: User) -> BookingParticipant:
    participant = BookingParticipant(
        booking_id=booking.id,
        user_id=user.id,
        status=ParticipantStatus.PENDING,
    )
    session.add(participant)
    # Notify booking creator
    await create_notification(
        session,
        recipient_id=booking.creator_id,
        type=NotificationType.BOOKING_JOINED,
        actor_id=user.id,
        target_type="booking",
        target_id=booking.id,
    )
    await session.commit()
    await session.refresh(participant)
    return participant


def count_accepted_participants(booking: Booking) -> int:
    return sum(1 for p in booking.participants if p.status == ParticipantStatus.ACCEPTED)


async def confirm_booking(session: AsyncSession, booking: Booking) -> Booking:
    booking.status = BookingStatus.CONFIRMED
    # Notify all participants except creator
    for p in booking.participants:
        if p.user_id != booking.creator_id and p.status == ParticipantStatus.ACCEPTED:
            await create_notification(
                session,
                recipient_id=p.user_id,
                type=NotificationType.BOOKING_CONFIRMED,
                actor_id=booking.creator_id,
                target_type="booking",
                target_id=booking.id,
            )
    # Create chat room for confirmed booking
    accepted_ids = [p.user_id for p in booking.participants if p.status == ParticipantStatus.ACCEPTED]
    court = booking.court or await session.get(Court, booking.court_id)
    court_name = court.name if court else ""
    await create_chat_room(session, booking=booking, participant_ids=accepted_ids, court_name=court_name)
    await session.commit()
    await session.refresh(booking)
    return booking


async def cancel_booking(session: AsyncSession, booking: Booking, user: User) -> Booking:
    """Cancel a booking. If user is creator, cancels the whole booking. Otherwise cancels their participation."""
    play_dt = datetime.combine(booking.play_date, booking.start_time, tzinfo=timezone.utc)

    # Check if weather allows penalty-free cancellation
    court = booking.court or await session.get(Court, booking.court_id)
    weather_free = False
    if court and court.latitude is not None and court.longitude is not None:
        weather_free = await check_free_cancel(
            lat=court.latitude,
            lon=court.longitude,
            play_date=booking.play_date,
            start_time=booking.start_time,
            court_id=booking.court_id,
        )

    if weather_free:
        cancel_reason = CreditReason.WEATHER_CANCEL
    else:
        cancel_reason = _get_cancel_reason(play_dt)

    if user.id == booking.creator_id:
        booking.status = BookingStatus.CANCELLED
        # Notify all accepted/pending participants (except creator)
        for p in booking.participants:
            if p.user_id != user.id and p.status in (ParticipantStatus.PENDING, ParticipantStatus.ACCEPTED):
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_CANCELLED,
                    actor_id=user.id,
                    target_type="booking",
                    target_id=booking.id,
                )
        await apply_credit_change(session, user, cancel_reason, description=f"Cancelled booking {booking.id}")
    else:
        for p in booking.participants:
            if p.user_id == user.id and p.status in (ParticipantStatus.PENDING, ParticipantStatus.ACCEPTED):
                p.status = ParticipantStatus.CANCELLED
                break
        await apply_credit_change(session, user, cancel_reason, description=f"Withdrew from booking {booking.id}")

    await session.commit()
    await session.refresh(booking)
    return booking


async def complete_booking(session: AsyncSession, booking: Booking) -> Booking:
    """Mark booking as completed and award credit to all accepted participants."""
    booking.status = BookingStatus.COMPLETED
    await session.flush()

    for p in booking.participants:
        if p.status == ParticipantStatus.ACCEPTED:
            user = p.user
            await apply_credit_change(session, user, CreditReason.ATTENDED, description=f"Attended booking {booking.id}")
            if p.user_id != booking.creator_id:
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_COMPLETED,
                    actor_id=booking.creator_id,
                    target_type="booking",
                    target_id=booking.id,
                )

    await session.commit()
    await session.refresh(booking)
    return booking


async def update_participant_status(
    session: AsyncSession, booking: Booking, user_id: uuid.UUID, new_status: str
) -> BookingParticipant | None:
    for p in booking.participants:
        if p.user_id == user_id:
            p.status = ParticipantStatus(new_status)
            # Notify participant of status change
            if new_status == "accepted":
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_ACCEPTED,
                    actor_id=booking.creator_id,
                    target_type="booking",
                    target_id=booking.id,
                )
            elif new_status == "rejected":
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_REJECTED,
                    actor_id=booking.creator_id,
                    target_type="booking",
                    target_id=booking.id,
                )
            await session.commit()
            await session.refresh(p)
            return p
    return None
