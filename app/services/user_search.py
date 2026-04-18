import math
import uuid
from datetime import date

from sqlalchemy import Float, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block import Block
from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.court import Court
from app.models.follow import Follow
from app.models.matching import MatchPreference, MatchPreferenceCourt
from app.models.user import User
from app.services.booking import _ntrp_to_float


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


async def search_users(
    session: AsyncSession,
    *,
    caller_id: uuid.UUID,
    keyword: str | None = None,
    city: str | None = None,
    gender: str | None = None,
    min_ntrp: str | None = None,
    max_ntrp: str | None = None,
    court_id: uuid.UUID | None = None,
    radius_km: float = 10.0,
    ideal_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Search users with filters, sorting, and pagination."""

    # --- Subqueries ---

    # Block subquery: user IDs blocked in either direction
    blocked_ids = (
        select(Block.blocked_id)
        .where(Block.blocker_id == caller_id)
        .union(
            select(Block.blocker_id).where(Block.blocked_id == caller_id)
        )
    ).scalar_subquery()

    # Last active: most recent completed booking play_date
    last_active_sq = (
        select(func.max(Booking.play_date))
        .join(BookingParticipant, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == User.id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
        .correlate(User)
        .scalar_subquery()
    )

    # Is following: whether caller follows this user
    is_following_sq = (
        select(func.count())
        .select_from(Follow)
        .where(
            Follow.follower_id == caller_id,
            Follow.followed_id == User.id,
        )
        .correlate(User)
        .scalar_subquery()
    )

    # --- Base query ---

    query = (
        select(
            User,
            last_active_sq.label("last_active_at"),
            case((is_following_sq > 0, True), else_=False).label("is_following"),
        )
        .where(
            User.id != caller_id,
            User.is_active == True,
            User.is_suspended == False,
            User.id.not_in(blocked_ids),
        )
    )

    # --- Optional filters ---

    if keyword:
        query = query.where(User.nickname.ilike(f"%{keyword}%"))

    if city:
        query = query.where(User.city == city)

    if gender:
        query = query.where(User.gender == gender)

    if min_ntrp:
        min_val = _ntrp_to_float(min_ntrp)
        # Filter using cast: compare base ntrp (strip +/-)
        query = query.where(
            func.cast(func.regexp_replace(User.ntrp_level, r"[+-]$", ""), Float) >= min_val
        )

    if max_ntrp:
        max_val = _ntrp_to_float(max_ntrp)
        query = query.where(
            func.cast(func.regexp_replace(User.ntrp_level, r"[+-]$", ""), Float) <= max_val
        )

    if ideal_only:
        query = query.where(User.is_ideal_player == True)

    # --- Court proximity filter ---

    if court_id:
        ref_court = await session.get(Court, court_id)
        if ref_court and ref_court.latitude is not None and ref_court.longitude is not None:
            # Find all courts within radius
            all_courts_result = await session.execute(
                select(Court.id, Court.latitude, Court.longitude).where(
                    Court.latitude.is_not(None),
                    Court.longitude.is_not(None),
                )
            )
            nearby_court_ids = []
            for cid, lat, lng in all_courts_result.all():
                if _haversine_km(ref_court.latitude, ref_court.longitude, lat, lng) <= radius_km:
                    nearby_court_ids.append(cid)

            if nearby_court_ids:
                # Users with completed bookings at nearby courts
                booking_users = (
                    select(BookingParticipant.user_id)
                    .join(Booking, Booking.id == BookingParticipant.booking_id)
                    .where(
                        Booking.court_id.in_(nearby_court_ids),
                        Booking.status == BookingStatus.COMPLETED,
                        BookingParticipant.status == ParticipantStatus.ACCEPTED,
                    )
                )
                # Users with match preferences listing nearby courts
                pref_users = (
                    select(MatchPreference.user_id)
                    .join(MatchPreferenceCourt, MatchPreferenceCourt.preference_id == MatchPreference.id)
                    .where(MatchPreferenceCourt.court_id.in_(nearby_court_ids))
                )
                court_user_ids = booking_users.union(pref_users).scalar_subquery()
                query = query.where(User.id.in_(court_user_ids))
            else:
                # No courts in range — return empty
                query = query.where(False)

    # --- Count total before pagination ---

    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # --- Sort and paginate ---

    query = query.order_by(
        User.is_ideal_player.desc(),
        last_active_sq.desc().nulls_last(),
    )

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await session.execute(query)
    rows = result.all()

    users = []
    for row in rows:
        user = row[0]
        users.append({
            "id": user.id,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "gender": user.gender.value,
            "city": user.city,
            "ntrp_level": user.ntrp_level,
            "ntrp_label": user.ntrp_label,
            "bio": user.bio,
            "years_playing": user.years_playing,
            "is_ideal_player": user.is_ideal_player,
            "is_following": row[2],
            "last_active_at": row[1],
        })

    return {"users": users, "total": total, "page": page, "page_size": page_size}
