import uuid
from collections import defaultdict
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


async def get_user_calendar(
    session: AsyncSession, user_id: uuid.UUID, year: int, month: int
) -> dict:
    """Return completed match dates for a user in a given month."""
    q = (
        select(
            Booking.id,
            Booking.play_date,
            Booking.match_type,
            Booking.start_time,
            Booking.end_time,
            Court.name.label("court_name"),
        )
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .join(Court, Court.id == Booking.court_id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
            func.extract("year", Booking.play_date) == year,
            func.extract("month", Booking.play_date) == month,
        )
        .order_by(Booking.play_date, Booking.start_time)
    )
    rows = (await session.execute(q)).all()

    booking_ids = [row[0] for row in rows]

    participants_by_booking: dict[uuid.UUID, list[dict]] = defaultdict(list)
    if booking_ids:
        p_q = (
            select(
                BookingParticipant.booking_id,
                User.id,
                User.nickname,
            )
            .join(User, User.id == BookingParticipant.user_id)
            .where(
                BookingParticipant.booking_id.in_(booking_ids),
                BookingParticipant.status == ParticipantStatus.ACCEPTED,
                BookingParticipant.user_id != user_id,
            )
        )
        p_rows = (await session.execute(p_q)).all()
        for p_row in p_rows:
            participants_by_booking[p_row[0]].append(
                {"user_id": p_row[1], "nickname": p_row[2]}
            )

    dates_map: dict[date, list[dict]] = defaultdict(list)
    for row in rows:
        booking_id, play_date, match_type, start_time, end_time, court_name = row
        dates_map[play_date].append(
            {
                "booking_id": booking_id,
                "court_name": court_name,
                "match_type": match_type.value,
                "start_time": start_time.strftime("%H:%M"),
                "end_time": end_time.strftime("%H:%M"),
                "participants": participants_by_booking.get(booking_id, []),
            }
        )

    match_dates = [
        {"date": d, "bookings": bookings}
        for d, bookings in sorted(dates_map.items())
    ]

    return {"year": year, "month": month, "match_dates": match_dates}
