import math
import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.block import Block
from app.models.booking import Booking, BookingStatus, GenderRequirement
from app.models.court import Court
from app.models.matching import (
    GenderPreference,
    MatchPreference,
    MatchPreferenceCourt,
    MatchTimeSlot,
    MatchTypePreference,
)
from app.models.user import Gender, User
from app.services.booking import _ntrp_to_float


async def create_preference(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    match_type: str = "any",
    min_ntrp: str,
    max_ntrp: str,
    gender_preference: str = "any",
    max_distance_km: float | None = None,
    time_slots: list[dict],
    court_ids: list[uuid.UUID],
) -> MatchPreference:
    # Check for existing preference
    existing = await session.execute(
        select(MatchPreference).where(MatchPreference.user_id == user_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError("preference_exists")

    pref = MatchPreference(
        user_id=user_id,
        match_type=MatchTypePreference(match_type),
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_preference=GenderPreference(gender_preference),
        max_distance_km=max_distance_km,
    )
    session.add(pref)
    await session.flush()

    for slot in time_slots:
        ts = MatchTimeSlot(
            preference_id=pref.id,
            day_of_week=slot["day_of_week"],
            start_time=slot["start_time"],
            end_time=slot["end_time"],
        )
        session.add(ts)

    for court_id in court_ids:
        pc = MatchPreferenceCourt(preference_id=pref.id, court_id=court_id)
        session.add(pc)

    await session.commit()
    return await get_preference_by_user(session, user_id)


async def get_preference_by_user(
    session: AsyncSession, user_id: uuid.UUID
) -> MatchPreference | None:
    result = await session.execute(
        select(MatchPreference)
        .options(
            selectinload(MatchPreference.time_slots),
            selectinload(MatchPreference.preferred_courts),
        )
        .where(MatchPreference.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_preference(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    match_type: str = "any",
    min_ntrp: str,
    max_ntrp: str,
    gender_preference: str = "any",
    max_distance_km: float | None = None,
    time_slots: list[dict],
    court_ids: list[uuid.UUID],
) -> MatchPreference:
    pref = await get_preference_by_user(session, user_id)
    if pref is None:
        raise ValueError("preference_not_found")

    pref.match_type = MatchTypePreference(match_type)
    pref.min_ntrp = min_ntrp
    pref.max_ntrp = max_ntrp
    pref.gender_preference = GenderPreference(gender_preference)
    pref.max_distance_km = max_distance_km

    # Replace time slots
    for ts in list(pref.time_slots):
        await session.delete(ts)
    await session.flush()

    for slot in time_slots:
        ts = MatchTimeSlot(
            preference_id=pref.id,
            day_of_week=slot["day_of_week"],
            start_time=slot["start_time"],
            end_time=slot["end_time"],
        )
        session.add(ts)

    # Replace preferred courts
    for pc in list(pref.preferred_courts):
        await session.delete(pc)
    await session.flush()

    for court_id in court_ids:
        pc = MatchPreferenceCourt(preference_id=pref.id, court_id=court_id)
        session.add(pc)

    await session.commit()
    session.expire(pref)
    return await get_preference_by_user(session, user_id)


async def toggle_preference(
    session: AsyncSession, user_id: uuid.UUID
) -> MatchPreference:
    pref = await get_preference_by_user(session, user_id)
    if pref is None:
        raise ValueError("preference_not_found")

    pref.is_active = not pref.is_active
    if pref.is_active:
        pref.last_active_at = datetime.now(timezone.utc)
    await session.commit()
    return await get_preference_by_user(session, user_id)


# --- Scoring ---


def _time_overlap_minutes(start_a: time, end_a: time, start_b: time, end_b: time) -> int:
    """Calculate overlap in minutes between two time ranges on the same day."""
    latest_start = max(start_a, start_b)
    earliest_end = min(end_a, end_b)
    if latest_start >= earliest_end:
        return 0
    delta = datetime.combine(datetime.min, earliest_end) - datetime.combine(datetime.min, latest_start)
    return int(delta.total_seconds() / 60)


def _compute_time_overlap_ratio(slots_a: list[MatchTimeSlot], slots_b: list[MatchTimeSlot]) -> float:
    """Compute the ratio of overlapping time to total available time for user A."""
    total_overlap = 0
    total_a = 0

    for sa in slots_a:
        slot_minutes = (
            datetime.combine(datetime.min, sa.end_time)
            - datetime.combine(datetime.min, sa.start_time)
        ).total_seconds() / 60
        total_a += slot_minutes

        for sb in slots_b:
            if sa.day_of_week == sb.day_of_week:
                total_overlap += _time_overlap_minutes(sa.start_time, sa.end_time, sb.start_time, sb.end_time)

    if total_a == 0:
        return 0.0
    return min(total_overlap / total_a, 1.0)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


async def compute_match_score(
    session: AsyncSession,
    user_a: User,
    pref_a: MatchPreference,
    user_b: User,
    pref_b: MatchPreference,
) -> float | None:
    """
    Compute match score between two users (0-100).
    Returns None if hard-filtered (incompatible).
    """
    # --- Hard filters ---

    # Gender check: A's preference vs B's gender and vice versa
    if pref_a.gender_preference == GenderPreference.MALE_ONLY and user_b.gender != Gender.MALE:
        return None
    if pref_a.gender_preference == GenderPreference.FEMALE_ONLY and user_b.gender != Gender.FEMALE:
        return None
    if pref_b.gender_preference == GenderPreference.MALE_ONLY and user_a.gender != Gender.MALE:
        return None
    if pref_b.gender_preference == GenderPreference.FEMALE_ONLY and user_a.gender != Gender.FEMALE:
        return None

    # NTRP gap check
    ntrp_a = _ntrp_to_float(user_a.ntrp_level)
    ntrp_b = _ntrp_to_float(user_b.ntrp_level)
    ntrp_gap = abs(ntrp_a - ntrp_b)
    if ntrp_gap > 1.5:
        return None

    # Time overlap check
    time_ratio = _compute_time_overlap_ratio(pref_a.time_slots, pref_b.time_slots)
    if time_ratio == 0:
        return None

    # --- Soft scoring ---
    weights = {"ntrp": 35, "time": 25, "court": 20, "credit": 10, "gender": 5, "ideal": 5}

    # NTRP score: full at +/-0.5, linear decay to 0 at +/-1.5
    if ntrp_gap <= 0.5:
        ntrp_score = 1.0
    else:
        ntrp_score = max(0.0, 1.0 - (ntrp_gap - 0.5) / 1.0)

    # Time score
    time_score = time_ratio

    # Court proximity score
    courts_a = pref_a.preferred_courts
    courts_b = pref_b.preferred_courts
    court_a_ids = {pc.court_id for pc in courts_a}
    court_b_ids = {pc.court_id for pc in courts_b}

    if not court_a_ids and not court_b_ids:
        # Neither has preferred courts — redistribute court weight
        court_score = 0.0
        redistributed = weights["court"]
        total_other = weights["ntrp"] + weights["time"] + weights["credit"] + weights["gender"] + weights["ideal"]
        weights["ntrp"] += redistributed * weights["ntrp"] / total_other
        weights["time"] += redistributed * weights["time"] / total_other
        weights["credit"] += redistributed * weights["credit"] / total_other
        weights["gender"] += redistributed * weights["gender"] / total_other
        weights["ideal"] += redistributed * weights["ideal"] / total_other
        weights["court"] = 0
    elif court_a_ids & court_b_ids:
        court_score = 1.0
    else:
        # Compute distance between nearest courts if both have lat/lng
        court_a_objs = []
        court_b_objs = []
        for pc in courts_a:
            result = await session.get(Court, pc.court_id)
            if result and result.latitude and result.longitude:
                court_a_objs.append(result)
        for pc in courts_b:
            result = await session.get(Court, pc.court_id)
            if result and result.latitude and result.longitude:
                court_b_objs.append(result)

        if court_a_objs and court_b_objs:
            min_dist = min(
                _haversine_km(ca.latitude, ca.longitude, cb.latitude, cb.longitude)
                for ca in court_a_objs
                for cb in court_b_objs
            )
            max_dist = pref_a.max_distance_km or 20.0  # default 20km
            court_score = max(0.0, 1.0 - min_dist / max_dist)
        else:
            court_score = 0.5  # Partial info, give neutral score

    # Credit score
    credit_score = user_b.credit_score / 100.0

    # Gender score (passed hard filter, so full score)
    gender_score = 1.0

    # Ideal player score
    ideal_score = 1.0 if user_b.is_ideal_player else 0.0

    total = (
        weights["ntrp"] * ntrp_score
        + weights["time"] * time_score
        + weights["court"] * court_score
        + weights["credit"] * credit_score
        + weights["gender"] * gender_score
        + weights["ideal"] * ideal_score
    )

    return round(total, 2)


# --- Candidate Search ---


async def search_candidates(
    session: AsyncSession,
    user: User,
    pref: MatchPreference,
    *,
    limit: int = 10,
) -> list[dict]:
    """Find and rank compatible users for user-to-user matching."""
    # Get all active preferences (excluding self, inactive, expired)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    result = await session.execute(
        select(MatchPreference)
        .options(
            selectinload(MatchPreference.time_slots),
            selectinload(MatchPreference.preferred_courts),
            selectinload(MatchPreference.user),
        )
        .where(
            MatchPreference.user_id != user.id,
            MatchPreference.is_active == True,  # noqa: E712
            MatchPreference.last_active_at >= thirty_days_ago,
        )
    )
    candidates_prefs = list(result.scalars().all())

    # Filter blocked users
    blocked_result = await session.execute(
        select(Block).where(
            or_(
                Block.blocker_id == user.id,
                Block.blocked_id == user.id,
            )
        )
    )
    blocked_pairs = blocked_result.scalars().all()
    blocked_ids = set()
    for b in blocked_pairs:
        blocked_ids.add(b.blocker_id)
        blocked_ids.add(b.blocked_id)
    blocked_ids.discard(user.id)

    scored = []
    for cp in candidates_prefs:
        candidate = cp.user
        if candidate.id in blocked_ids:
            continue
        if candidate.is_suspended:
            continue

        score = await compute_match_score(session, user, pref, candidate, cp)
        if score is not None:
            scored.append({
                "user_id": str(candidate.id),
                "nickname": candidate.nickname,
                "gender": candidate.gender.value,
                "ntrp_level": candidate.ntrp_level,
                "ntrp_label": candidate.ntrp_label,
                "credit_score": candidate.credit_score,
                "is_ideal_player": candidate.is_ideal_player,
                "city": candidate.city,
                "score": score,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


async def search_booking_recommendations(
    session: AsyncSession,
    user: User,
    pref: MatchPreference,
    *,
    limit: int = 10,
) -> list[dict]:
    """Find open bookings matching user's preferences."""
    # Get open bookings not created by self
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.creator),
            selectinload(Booking.court),
        )
        .where(
            Booking.status == BookingStatus.OPEN,
            Booking.creator_id != user.id,
            Booking.play_date >= datetime.now(timezone.utc).date(),
        )
    )
    bookings = list(result.scalars().all())

    # Filter blocked
    blocked_result = await session.execute(
        select(Block).where(
            or_(
                Block.blocker_id == user.id,
                Block.blocked_id == user.id,
            )
        )
    )
    blocked_pairs = blocked_result.scalars().all()
    blocked_ids = set()
    for b in blocked_pairs:
        blocked_ids.add(b.blocker_id)
        blocked_ids.add(b.blocked_id)
    blocked_ids.discard(user.id)

    user_ntrp = _ntrp_to_float(user.ntrp_level)

    scored = []
    for booking in bookings:
        if booking.creator_id in blocked_ids:
            continue
        if booking.creator.is_suspended:
            continue

        # Gender hard filter
        if booking.gender_requirement == GenderRequirement.MALE_ONLY and user.gender != Gender.MALE:
            continue
        if booking.gender_requirement == GenderRequirement.FEMALE_ONLY and user.gender != Gender.FEMALE:
            continue

        # NTRP hard filter
        booking_min = _ntrp_to_float(booking.min_ntrp)
        booking_max = _ntrp_to_float(booking.max_ntrp)
        if user_ntrp < booking_min - 0.05 or user_ntrp > booking_max + 0.05:
            continue

        # Time overlap: check if booking day/time overlaps with any user time slot
        booking_dow = booking.play_date.weekday()
        has_time_overlap = False
        for slot in pref.time_slots:
            if slot.day_of_week == booking_dow:
                overlap = _time_overlap_minutes(slot.start_time, slot.end_time, booking.start_time, booking.end_time)
                if overlap > 0:
                    has_time_overlap = True
                    break
        if not has_time_overlap:
            continue

        # Score the booking
        booking_mid = (booking_min + booking_max) / 2
        ntrp_gap = abs(user_ntrp - booking_mid)
        ntrp_score = 1.0 if ntrp_gap <= 0.5 else max(0.0, 1.0 - (ntrp_gap - 0.5))

        # Court match
        pref_court_ids = {pc.court_id for pc in pref.preferred_courts}
        court_score = 1.0 if booking.court_id in pref_court_ids else 0.3

        # Credit score of creator
        credit_s = booking.creator.credit_score / 100.0

        # Ideal player
        ideal_s = 1.0 if booking.creator.is_ideal_player else 0.0

        total = 35 * ntrp_score + 25 * 1.0 + 20 * court_score + 10 * credit_s + 5 * 1.0 + 5 * ideal_s
        total = round(total, 2)

        scored.append({
            "booking_id": str(booking.id),
            "creator_id": str(booking.creator_id),
            "creator_nickname": booking.creator.nickname,
            "court_id": str(booking.court_id),
            "court_name": booking.court.name,
            "match_type": booking.match_type.value,
            "play_date": booking.play_date.isoformat(),
            "start_time": booking.start_time.isoformat(),
            "end_time": booking.end_time.isoformat(),
            "min_ntrp": booking.min_ntrp,
            "max_ntrp": booking.max_ntrp,
            "gender_requirement": booking.gender_requirement.value,
            "score": total,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
