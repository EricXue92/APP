import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import (
    Booking,
    BookingParticipant,
    BookingStatus,
    MatchType,
    ParticipantStatus,
)
from app.models.court import Court
from app.models.user import User


async def get_user_stats(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """Compute playing statistics for a user from completed bookings."""
    # Base condition: user participated and was accepted, booking was completed
    base_join = (
        select(Booking.id)
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
    )

    # 1. total_matches
    total_q = select(func.count()).select_from(base_join.subquery())
    total_matches = (await session.execute(total_q)).scalar() or 0

    # 2. monthly_matches (current calendar month)
    today = date.today()
    monthly_q = select(func.count()).select_from(
        base_join.where(
            func.extract("year", Booking.play_date) == today.year,
            func.extract("month", Booking.play_date) == today.month,
        ).subquery()
    )
    monthly_matches = (await session.execute(monthly_q)).scalar() or 0

    # 3. singles_count / doubles_count
    type_q = (
        select(Booking.match_type, func.count())
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
        .group_by(Booking.match_type)
    )
    type_rows = (await session.execute(type_q)).all()
    type_counts = {row[0]: row[1] for row in type_rows}
    singles_count = type_counts.get(MatchType.SINGLES, 0)
    doubles_count = type_counts.get(MatchType.DOUBLES, 0)

    # 4. top_courts (top 3)
    court_q = (
        select(Court.id, Court.name, func.count().label("cnt"))
        .join(Booking, Booking.court_id == Court.id)
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
        .group_by(Court.id, Court.name)
        .order_by(func.count().desc())
        .limit(3)
    )
    court_rows = (await session.execute(court_q)).all()
    top_courts = [
        {"court_id": row[0], "court_name": row[1], "match_count": row[2]}
        for row in court_rows
    ]

    # 5. top_partners (top 3, excluding self)
    user_bookings = (
        select(BookingParticipant.booking_id)
        .join(Booking, Booking.id == BookingParticipant.booking_id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
        .scalar_subquery()
    )
    partner_q = (
        select(User.id, User.nickname, User.avatar_url, func.count().label("cnt"))
        .join(BookingParticipant, BookingParticipant.user_id == User.id)
        .where(
            BookingParticipant.booking_id.in_(user_bookings),
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            BookingParticipant.user_id != user_id,
        )
        .group_by(User.id, User.nickname, User.avatar_url)
        .order_by(func.count().desc())
        .limit(3)
    )
    partner_rows = (await session.execute(partner_q)).all()
    top_partners = [
        {
            "user_id": row[0],
            "nickname": row[1],
            "avatar_url": row[2],
            "match_count": row[3],
        }
        for row in partner_rows
    ]

    return {
        "total_matches": total_matches,
        "monthly_matches": monthly_matches,
        "singles_count": singles_count,
        "doubles_count": doubles_count,
        "top_courts": top_courts,
        "top_partners": top_partners,
    }
