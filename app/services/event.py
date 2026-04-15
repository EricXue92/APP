import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.block import Block
from app.models.event import (
    Event,
    EventMatch,
    EventMatchStatus,
    EventParticipant,
    EventParticipantStatus,
    EventSet,
    EventStatus,
    EventType,
)
from app.models.notification import NotificationType
from app.models.user import Gender, User
from app.services.notification import create_notification


def _ntrp_to_float(level: str) -> float:
    base = level.rstrip("+-")
    value = float(base)
    if level.endswith("+"):
        value += 0.05
    elif level.endswith("-"):
        value -= 0.05
    return value


async def create_event(
    session: AsyncSession,
    *,
    creator: User,
    name: str,
    event_type: str,
    min_ntrp: str,
    max_ntrp: str,
    gender_requirement: str = "any",
    max_participants: int,
    games_per_set: int = 6,
    num_sets: int = 3,
    match_tiebreak: bool = False,
    start_date=None,
    end_date=None,
    registration_deadline: datetime,
    entry_fee: int | None = None,
    description: str | None = None,
) -> Event:
    event = Event(
        creator_id=creator.id,
        name=name,
        event_type=EventType(event_type),
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        gender_requirement=gender_requirement,
        max_participants=max_participants,
        games_per_set=games_per_set,
        num_sets=num_sets,
        match_tiebreak=match_tiebreak,
        start_date=start_date,
        end_date=end_date,
        registration_deadline=registration_deadline,
        entry_fee=entry_fee,
        description=description,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def get_event_by_id(session: AsyncSession, event_id: uuid.UUID) -> Event | None:
    result = await session.execute(
        select(Event)
        .options(
            selectinload(Event.participants).selectinload(EventParticipant.user),
            selectinload(Event.creator),
        )
        .where(Event.id == event_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def list_events(
    session: AsyncSession,
    *,
    status: str | None = None,
    event_type: str | None = None,
    current_user_id: uuid.UUID | None = None,
) -> list[Event]:
    query = select(Event).join(User, Event.creator_id == User.id)

    if status:
        query = query.where(Event.status == EventStatus(status))
    else:
        # By default show open and in_progress events
        query = query.where(Event.status.in_([EventStatus.OPEN, EventStatus.IN_PROGRESS]))

    if event_type:
        query = query.where(Event.event_type == EventType(event_type))

    if current_user_id:
        blocked_ids = select(Block.blocked_id).where(Block.blocker_id == current_user_id)
        blocker_ids = select(Block.blocker_id).where(Block.blocked_id == current_user_id)
        query = query.where(
            Event.creator_id.notin_(blocked_ids),
            Event.creator_id.notin_(blocker_ids),
        )

    query = query.order_by(User.is_ideal_player.desc(), Event.registration_deadline)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_my_events(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[Event]:
    created = select(Event.id).where(Event.creator_id == user_id)
    joined = select(EventParticipant.event_id).where(EventParticipant.user_id == user_id)
    query = (
        select(Event)
        .where(Event.id.in_(created.union(joined)))
        .order_by(Event.created_at.desc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_event(
    session: AsyncSession,
    event: Event,
    **kwargs,
) -> Event:
    for key, value in kwargs.items():
        if value is not None:
            setattr(event, key, value)
    await session.commit()
    await session.refresh(event)
    return event
