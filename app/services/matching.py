import uuid
from datetime import datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.matching import (
    GenderPreference,
    MatchPreference,
    MatchPreferenceCourt,
    MatchTimeSlot,
    MatchTypePreference,
)


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
