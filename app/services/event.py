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
    query = (
        select(Event)
        .join(User, Event.creator_id == User.id)
        .options(selectinload(Event.participants))
    )

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
        .options(selectinload(Event.participants))
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


async def publish_event(session: AsyncSession, event: Event) -> Event:
    event.status = EventStatus.OPEN
    await session.commit()
    await session.refresh(event)
    return event


async def join_event(
    session: AsyncSession,
    event: Event,
    user: User,
    lang: str = "en",
) -> Event:
    from app.i18n import t
    from app.services.block import is_blocked

    if event.status != EventStatus.OPEN:
        raise ValueError(t("event.not_open", lang))

    # Check already joined
    for p in event.participants:
        if p.user_id == user.id and p.status != EventParticipantStatus.WITHDRAWN:
            raise LookupError(t("event.already_joined", lang))

    # Check NTRP
    user_ntrp = _ntrp_to_float(user.ntrp_level)
    if user_ntrp < _ntrp_to_float(event.min_ntrp) or user_ntrp > _ntrp_to_float(event.max_ntrp):
        raise PermissionError(t("event.ntrp_out_of_range", lang))

    # Check gender
    if event.gender_requirement == "male_only" and user.gender != Gender.MALE:
        raise PermissionError(t("event.gender_mismatch", lang))
    if event.gender_requirement == "female_only" and user.gender != Gender.FEMALE:
        raise PermissionError(t("event.gender_mismatch", lang))

    # Check block
    if await is_blocked(session, user.id, event.creator_id):
        raise PermissionError(t("block.user_blocked", lang))

    # Check capacity
    active_count = sum(1 for p in event.participants if p.status == EventParticipantStatus.REGISTERED)
    if active_count >= event.max_participants:
        raise LookupError(t("event.full", lang))

    participant = EventParticipant(
        event_id=event.id,
        user_id=user.id,
    )
    session.add(participant)

    # Notify organizer
    await create_notification(
        session,
        recipient_id=event.creator_id,
        type=NotificationType.EVENT_JOINED,
        actor_id=user.id,
        target_type="event",
        target_id=event.id,
    )

    await session.commit()
    event = await get_event_by_id(session, event.id)
    return event


async def withdraw_from_event(
    session: AsyncSession,
    event: Event,
    user: User,
    lang: str = "en",
) -> Event:
    from app.i18n import t

    if event.status not in (EventStatus.OPEN, EventStatus.DRAFT):
        raise ValueError(t("event.cannot_withdraw", lang))

    for p in event.participants:
        if p.user_id == user.id and p.status == EventParticipantStatus.REGISTERED:
            p.status = EventParticipantStatus.WITHDRAWN
            await session.commit()
            event = await get_event_by_id(session, event.id)
            return event

    raise ValueError(t("event.not_registered", lang))


async def remove_participant(
    session: AsyncSession,
    event: Event,
    target_user_id: uuid.UUID,
    lang: str = "en",
) -> Event:
    from app.i18n import t

    for p in event.participants:
        if p.user_id == target_user_id and p.status == EventParticipantStatus.REGISTERED:
            p.status = EventParticipantStatus.WITHDRAWN
            await session.commit()
            event = await get_event_by_id(session, event.id)
            return event

    raise ValueError(t("event.not_registered", lang))


# --- Seeding + Draw Generation ---

import math
import random

from app.services.chat import create_event_chat_room


def _seed_participants(participants: list[EventParticipant]) -> list[EventParticipant]:
    """Sort participants by NTRP desc, credit_score desc, then random. Assign seed numbers."""
    def sort_key(p):
        return (-_ntrp_to_float(p.user.ntrp_level), -p.user.credit_score, random.random())

    sorted_p = sorted(participants, key=sort_key)
    for i, p in enumerate(sorted_p):
        p.seed = i + 1
    return sorted_p


def _generate_elimination_draw(
    seeded: list[EventParticipant],
) -> list[dict]:
    """Generate elimination bracket matches. Returns list of match dicts."""
    n = len(seeded)
    bracket_size = 2 ** math.ceil(math.log2(n))
    total_rounds = int(math.log2(bracket_size))

    # Place seeds into bracket positions
    positions = [None] * bracket_size

    if n >= 1:
        positions[0] = seeded[0]
    if n >= 2:
        positions[bracket_size - 1] = seeded[1]
    if n >= 3:
        positions[bracket_size // 2] = seeded[2]
    if n >= 4:
        positions[bracket_size // 2 - 1] = seeded[3]

    # Fill remaining seeds randomly into empty positions
    remaining = seeded[4:] if n > 4 else []
    empty_indices = [i for i, p in enumerate(positions) if p is None]
    random.shuffle(empty_indices)

    for i, p in enumerate(remaining):
        positions[empty_indices[i]] = p

    matches = []
    # Generate round 1
    for i in range(0, bracket_size, 2):
        match_order = i // 2 + 1
        player_a = positions[i]
        player_b = positions[i + 1]

        a_id = player_a.user_id if player_a else None
        b_id = player_b.user_id if player_b else None

        is_bye = a_id is None or b_id is None
        winner = a_id or b_id if is_bye else None
        bye_status = EventMatchStatus.CONFIRMED if is_bye else EventMatchStatus.PENDING

        matches.append({
            "round": 1,
            "match_order": match_order,
            "player_a_id": a_id,
            "player_b_id": b_id,
            "winner_id": winner,
            "status": bye_status,
        })

    # Generate subsequent rounds (empty shells)
    for r in range(2, total_rounds + 1):
        matches_in_round = bracket_size // (2 ** r)
        for m in range(1, matches_in_round + 1):
            matches.append({
                "round": r,
                "match_order": m,
                "player_a_id": None,
                "player_b_id": None,
                "winner_id": None,
                "status": EventMatchStatus.PENDING,
            })

    return matches


def _generate_round_robin_draw(seeded: list[EventParticipant]) -> list[dict]:
    """Generate round-robin matches with snake-draft grouping."""
    n = len(seeded)
    if n <= 4:
        num_groups = 1
    else:
        num_groups = max(2, n // 4)

    # Snake-draft into groups
    groups: dict[str, list[EventParticipant]] = {}
    group_labels = [chr(ord("A") + i) for i in range(num_groups)]
    for label in group_labels:
        groups[label] = []

    for i, p in enumerate(seeded):
        cycle = i // num_groups
        idx = i % num_groups
        if cycle % 2 == 1:
            idx = num_groups - 1 - idx
        label = group_labels[idx]
        groups[label].append(p)
        p.group_name = label

    matches = []
    for label, members in groups.items():
        group_matches = _round_robin_schedule(members, label)
        matches.extend(group_matches)

    return matches


def _round_robin_schedule(members: list[EventParticipant], group_name: str) -> list[dict]:
    """Generate all-play-all matches using circle method."""
    n = len(members)
    if n < 2:
        return []

    players = list(members)
    if n % 2 == 1:
        players.append(None)  # Dummy for bye

    num_rounds = len(players) - 1
    matches = []
    match_order = 1

    for round_num in range(1, num_rounds + 1):
        for i in range(len(players) // 2):
            a = players[i]
            b = players[len(players) - 1 - i]
            if a is None or b is None:
                continue
            matches.append({
                "round": round_num,
                "match_order": match_order,
                "player_a_id": a.user_id,
                "player_b_id": b.user_id,
                "winner_id": None,
                "group_name": group_name,
                "status": EventMatchStatus.PENDING,
            })
            match_order += 1

        # Rotate: fix first player, rotate rest
        players = [players[0]] + [players[-1]] + players[1:-1]

    return matches


async def start_event(
    session: AsyncSession,
    event: Event,
    lang: str = "en",
) -> Event:
    from app.i18n import t

    if event.status != EventStatus.OPEN:
        raise ValueError(t("event.cannot_modify", lang))

    active_participants = [p for p in event.participants if p.status == EventParticipantStatus.REGISTERED]
    is_elimination = event.event_type in (EventType.SINGLES_ELIMINATION, EventType.DOUBLES_ELIMINATION)
    min_required = 4 if is_elimination else 3

    if len(active_participants) < min_required:
        raise ValueError(t("event.not_enough_participants", lang))

    seeded = _seed_participants(active_participants)

    if is_elimination:
        match_dicts = _generate_elimination_draw(seeded)
    else:
        match_dicts = _generate_round_robin_draw(seeded)

    for md in match_dicts:
        match = EventMatch(
            event_id=event.id,
            round=md["round"],
            match_order=md["match_order"],
            player_a_id=md["player_a_id"],
            player_b_id=md["player_b_id"],
            winner_id=md.get("winner_id"),
            group_name=md.get("group_name"),
            status=md["status"],
        )
        session.add(match)

    if is_elimination:
        await session.flush()
        await _advance_bye_winners(session, event)

    for p in active_participants:
        p.status = EventParticipantStatus.CONFIRMED

    event.status = EventStatus.IN_PROGRESS
    await session.flush()

    participant_ids = [p.user_id for p in active_participants]
    await create_event_chat_room(session, event=event, participant_ids=participant_ids)

    for p in active_participants:
        if p.user_id != event.creator_id:
            await create_notification(
                session,
                recipient_id=p.user_id,
                type=NotificationType.EVENT_STARTED,
                actor_id=event.creator_id,
                target_type="event",
                target_id=event.id,
            )

    await session.commit()
    event = await get_event_by_id(session, event.id)
    return event


async def _advance_bye_winners(session: AsyncSession, event: Event) -> None:
    """For elimination: fill round 2 slots with BYE winners from round 1."""
    result = await session.execute(
        select(EventMatch)
        .where(EventMatch.event_id == event.id)
        .order_by(EventMatch.round, EventMatch.match_order)
    )
    all_matches = list(result.scalars().all())

    round1 = [m for m in all_matches if m.round == 1]
    round2 = [m for m in all_matches if m.round == 2]

    for i, r2_match in enumerate(round2):
        r1_a = round1[i * 2]
        r1_b = round1[i * 2 + 1]

        if r1_a.winner_id is not None:
            r2_match.player_a_id = r1_a.winner_id
        if r1_b.winner_id is not None:
            r2_match.player_b_id = r1_b.winner_id

    await session.flush()


async def get_event_matches(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    round: int | None = None,
    group_name: str | None = None,
) -> list[EventMatch]:
    query = (
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.event_id == event_id)
    )
    if round is not None:
        query = query.where(EventMatch.round == round)
    if group_name is not None:
        query = query.where(EventMatch.group_name == group_name)
    query = query.order_by(EventMatch.round, EventMatch.match_order)
    result = await session.execute(query)
    return list(result.scalars().all())
