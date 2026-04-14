import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.notification import NotificationType
from app.models.review import Review
from app.models.user import User
from app.services.notification import create_notification

CREDIT_THRESHOLD = 90
MIN_COMPLETED_BOOKINGS = 10
MIN_AVG_RATING = 4.0


async def evaluate_ideal_status(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Evaluate and update ideal player status. Returns the new status."""
    user = await session.get(User, user_id)
    if user is None:
        return False

    was_ideal = user.is_ideal_player
    is_ideal = await _check_conditions(session, user)
    user.is_ideal_player = is_ideal

    if is_ideal != was_ideal:
        await create_notification(
            session,
            recipient_id=user_id,
            type=(
                NotificationType.IDEAL_PLAYER_GAINED
                if is_ideal
                else NotificationType.IDEAL_PLAYER_LOST
            ),
        )

    return is_ideal


async def _check_conditions(session: AsyncSession, user: User) -> bool:
    if user.credit_score < CREDIT_THRESHOLD:
        return False
    if user.cancel_count != 0:
        return False

    completed = await _count_completed_bookings(session, user.id)
    if completed < MIN_COMPLETED_BOOKINGS:
        return False

    avg = await _avg_review_rating(session, user.id)
    if avg is None or avg < MIN_AVG_RATING:
        return False

    return True


async def _count_completed_bookings(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(BookingParticipant.id))
        .join(Booking, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
    )
    return result.scalar_one()


async def _avg_review_rating(session: AsyncSession, user_id: uuid.UUID) -> float | None:
    """Average of all three rating dimensions across all non-hidden reviews received."""
    result = await session.execute(
        select(
            func.avg(
                (Review.skill_rating + Review.punctuality_rating + Review.sportsmanship_rating)
                / 3.0
            )
        ).where(
            Review.reviewee_id == user_id,
            Review.is_hidden == False,  # noqa: E712
        )
    )
    val = result.scalar_one()
    return float(val) if val is not None else None
