import uuid
from datetime import datetime, timezone

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


async def get_match_by_id(session: AsyncSession, match_id: uuid.UUID) -> EventMatch | None:
    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match_id)
    )
    return result.scalar_one_or_none()


# --- Score Validation ---


def validate_set_score(score_a: int, score_b: int, tiebreak_a: int | None, tiebreak_b: int | None, games_per_set: int, is_match_tiebreak: bool = False) -> bool:
    if is_match_tiebreak:
        if not ((score_a == 1 and score_b == 0) or (score_a == 0 and score_b == 1)):
            return False
        if tiebreak_a is None or tiebreak_b is None:
            return False
        winner_tb = max(tiebreak_a, tiebreak_b)
        loser_tb = min(tiebreak_a, tiebreak_b)
        if winner_tb < 10:
            return False
        if winner_tb - loser_tb < 2:
            return False
        return True

    g = games_per_set
    high = max(score_a, score_b)
    low = min(score_a, score_b)

    # Normal win: winner has g games, lead by >= 2
    if high == g and low <= g - 2:
        if tiebreak_a is not None or tiebreak_b is not None:
            return False
        return True

    # Tiebreak: g+1 vs g
    if high == g + 1 and low == g:
        if tiebreak_a is None or tiebreak_b is None:
            return False
        winner_tb = max(tiebreak_a, tiebreak_b)
        loser_tb = min(tiebreak_a, tiebreak_b)
        if winner_tb < 7:
            return False
        if winner_tb - loser_tb < 2:
            return False
        return True

    return False


def validate_match_score(sets: list[dict], games_per_set: int, num_sets: int, match_tiebreak: bool) -> str | None:
    """Validate all sets and determine winner. Returns 'a' or 'b', or None if invalid."""
    sets_to_win = (num_sets // 2) + 1
    a_wins = 0
    b_wins = 0

    for i, s in enumerate(sets):
        is_deciding_set = (i == num_sets - 1) and match_tiebreak and (a_wins == sets_to_win - 1) and (b_wins == sets_to_win - 1)

        if not validate_set_score(s["score_a"], s["score_b"], s.get("tiebreak_a"), s.get("tiebreak_b"), games_per_set, is_match_tiebreak=is_deciding_set):
            return None

        if s["score_a"] > s["score_b"]:
            a_wins += 1
        elif s["score_b"] > s["score_a"]:
            b_wins += 1
        else:
            return None  # Tie in a set is invalid

    if a_wins >= sets_to_win:
        return "a"
    if b_wins >= sets_to_win:
        return "b"

    return None


async def submit_score(
    session: AsyncSession,
    match: EventMatch,
    submitter_id: uuid.UUID,
    sets_data: list[dict],
    lang: str = "en",
) -> EventMatch:
    from app.i18n import t

    if match.status not in (EventMatchStatus.PENDING,):
        raise ValueError(t("event.score_already_submitted", lang))

    if match.player_a_id is None or match.player_b_id is None:
        raise ValueError(t("event.match_not_ready", lang))

    if submitter_id not in (match.player_a_id, match.player_b_id):
        raise PermissionError(t("event.not_match_player", lang))

    event = await get_event_by_id(session, match.event_id)

    winner_side = validate_match_score(
        sets_data,
        games_per_set=event.games_per_set,
        num_sets=event.num_sets,
        match_tiebreak=event.match_tiebreak,
    )
    if winner_side is None:
        raise ValueError(t("event.score_invalid", lang))

    winner_id = match.player_a_id if winner_side == "a" else match.player_b_id

    for s in sets_data:
        event_set = EventSet(
            match_id=match.id,
            set_number=s["set_number"],
            score_a=s["score_a"],
            score_b=s["score_b"],
            tiebreak_a=s.get("tiebreak_a"),
            tiebreak_b=s.get("tiebreak_b"),
        )
        session.add(event_set)

    match.status = EventMatchStatus.SUBMITTED
    match.submitted_by = submitter_id
    match.winner_id = winner_id

    opponent_id = match.player_b_id if submitter_id == match.player_a_id else match.player_a_id
    await create_notification(
        session,
        recipient_id=opponent_id,
        type=NotificationType.EVENT_SCORE_SUBMITTED,
        actor_id=submitter_id,
        target_type="event_match",
        target_id=match.id,
    )

    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def confirm_score(
    session: AsyncSession,
    match: EventMatch,
    user_id: uuid.UUID,
    lang: str = "en",
) -> EventMatch:
    from app.i18n import t

    if match.status != EventMatchStatus.SUBMITTED:
        raise ValueError(t("event.match_not_submitted", lang))

    if user_id not in (match.player_a_id, match.player_b_id):
        raise PermissionError(t("event.not_match_player", lang))

    if user_id == match.submitted_by:
        raise ValueError(t("event.cannot_confirm_own", lang))

    match.status = EventMatchStatus.CONFIRMED
    match.confirmed_at = datetime.now(timezone.utc)

    # Notify submitter
    await create_notification(
        session,
        recipient_id=match.submitted_by,
        type=NotificationType.EVENT_SCORE_CONFIRMED,
        actor_id=user_id,
        target_type="event_match",
        target_id=match.id,
    )

    await session.flush()

    # Auto-advance for elimination tournaments
    event = await get_event_by_id(session, match.event_id)
    if event.event_type in (EventType.SINGLES_ELIMINATION, EventType.DOUBLES_ELIMINATION):
        await _advance_winner(session, event, match)

    # Check if all matches are done → complete event
    await _check_event_completion(session, event)

    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def dispute_score(
    session: AsyncSession,
    match: EventMatch,
    user_id: uuid.UUID,
    lang: str = "en",
) -> EventMatch:
    from app.i18n import t

    if match.status != EventMatchStatus.SUBMITTED:
        raise ValueError(t("event.match_not_submitted", lang))

    if user_id not in (match.player_a_id, match.player_b_id):
        raise PermissionError(t("event.not_match_player", lang))

    if user_id == match.submitted_by:
        raise ValueError(t("event.cannot_confirm_own", lang))

    match.status = EventMatchStatus.DISPUTED

    # Notify event organizer
    event = await get_event_by_id(session, match.event_id)
    await create_notification(
        session,
        recipient_id=event.creator_id,
        type=NotificationType.EVENT_SCORE_DISPUTED,
        actor_id=user_id,
        target_type="event_match",
        target_id=match.id,
    )

    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _advance_winner(session: AsyncSession, event: Event, match: EventMatch) -> None:
    """For elimination: fill the winner into the next round match."""
    all_matches = await get_event_matches(session, event.id)
    current_round = [m for m in all_matches if m.round == match.round]
    next_round = [m for m in all_matches if m.round == match.round + 1]

    if not next_round:
        return  # This was the final

    # Find this match's position in current round
    current_round.sort(key=lambda m: m.match_order)
    match_idx = next(i for i, m in enumerate(current_round) if m.id == match.id)

    # Determine which next-round match and slot
    next_match_idx = match_idx // 2
    slot = "a" if match_idx % 2 == 0 else "b"

    next_round.sort(key=lambda m: m.match_order)
    next_match = next_round[next_match_idx]

    if slot == "a":
        next_match.player_a_id = match.winner_id
    else:
        next_match.player_b_id = match.winner_id

    await session.flush()

    # If both players are now set, notify them
    if next_match.player_a_id and next_match.player_b_id:
        for pid in [next_match.player_a_id, next_match.player_b_id]:
            await create_notification(
                session,
                recipient_id=pid,
                type=NotificationType.EVENT_MATCH_READY,
                actor_id=event.creator_id,
                target_type="event_match",
                target_id=next_match.id,
            )

    # Notify eliminated loser
    loser_id = match.player_a_id if match.winner_id == match.player_b_id else match.player_b_id
    if loser_id:
        await create_notification(
            session,
            recipient_id=loser_id,
            type=NotificationType.EVENT_ELIMINATED,
            actor_id=event.creator_id,
            target_type="event",
            target_id=event.id,
        )
        # Mark loser as eliminated
        for p in event.participants:
            if p.user_id == loser_id:
                p.status = EventParticipantStatus.ELIMINATED
                break


async def _check_event_completion(session: AsyncSession, event: Event) -> None:
    """Check if all matches are decided. If so, mark event as completed."""
    all_matches = await get_event_matches(session, event.id)
    all_decided = all(m.status in (EventMatchStatus.CONFIRMED, EventMatchStatus.WALKOVER) for m in all_matches)

    if all_decided and event.status == EventStatus.IN_PROGRESS:
        event.status = EventStatus.COMPLETED

        from app.services.chat import set_event_room_readonly
        await set_event_room_readonly(session, event_id=event.id)

        # Notify all participants
        for p in event.participants:
            if p.status in (EventParticipantStatus.CONFIRMED, EventParticipantStatus.ELIMINATED):
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.EVENT_COMPLETED,
                    actor_id=event.creator_id,
                    target_type="event",
                    target_id=event.id,
                )


async def submit_walkover(
    session: AsyncSession,
    match: EventMatch,
    submitter_id: uuid.UUID,
    lang: str = "en",
) -> EventMatch:
    """Submit a walkover claim. Goes through same submitted->confirmed flow."""
    from app.i18n import t

    if match.status not in (EventMatchStatus.PENDING,):
        raise ValueError(t("event.walkover_already_decided", lang))

    if match.player_a_id is None or match.player_b_id is None:
        raise ValueError(t("event.match_not_ready", lang))

    if submitter_id not in (match.player_a_id, match.player_b_id):
        raise PermissionError(t("event.not_match_player", lang))

    # Submitter claims they showed up, opponent didn't -> submitter wins
    match.winner_id = submitter_id
    match.status = EventMatchStatus.SUBMITTED
    match.submitted_by = submitter_id

    # Create a 0-0 set to record the walkover
    event_set = EventSet(
        match_id=match.id,
        set_number=1,
        score_a=0,
        score_b=0,
    )
    session.add(event_set)

    # Notify opponent
    opponent_id = match.player_b_id if submitter_id == match.player_a_id else match.player_a_id
    await create_notification(
        session,
        recipient_id=opponent_id,
        type=NotificationType.EVENT_WALKOVER,
        actor_id=submitter_id,
        target_type="event_match",
        target_id=match.id,
    )

    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def organizer_set_score(
    session: AsyncSession,
    match: EventMatch,
    organizer_id: uuid.UUID,
    sets_data: list[dict],
    lang: str = "en",
) -> EventMatch:
    """Organizer directly sets score — auto-confirmed, no dual confirmation needed."""
    from app.i18n import t

    event = await get_event_by_id(session, match.event_id)
    if event.creator_id != organizer_id:
        raise PermissionError(t("event.not_creator", lang))

    # Delete existing sets if overriding
    for s in list(match.sets):
        await session.delete(s)
    await session.flush()

    # Validate scores
    winner_side = validate_match_score(
        sets_data,
        games_per_set=event.games_per_set,
        num_sets=event.num_sets,
        match_tiebreak=event.match_tiebreak,
    )
    if winner_side is None:
        raise ValueError(t("event.score_invalid", lang))

    winner_id = match.player_a_id if winner_side == "a" else match.player_b_id

    for s in sets_data:
        event_set = EventSet(
            match_id=match.id,
            set_number=s["set_number"],
            score_a=s["score_a"],
            score_b=s["score_b"],
            tiebreak_a=s.get("tiebreak_a"),
            tiebreak_b=s.get("tiebreak_b"),
        )
        session.add(event_set)

    match.winner_id = winner_id
    match.status = EventMatchStatus.CONFIRMED
    match.confirmed_at = datetime.now(timezone.utc)

    await session.flush()

    # Auto-advance for elimination
    if event.event_type in (EventType.SINGLES_ELIMINATION, EventType.DOUBLES_ELIMINATION):
        await _advance_winner(session, event, match)

    await _check_event_completion(session, event)
    await session.commit()

    result = await session.execute(
        select(EventMatch)
        .options(selectinload(EventMatch.sets))
        .where(EventMatch.id == match.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def get_bracket(session: AsyncSession, event_id: uuid.UUID) -> dict:
    """Return elimination bracket organized by rounds."""
    matches = await get_event_matches(session, event_id)

    rounds_dict: dict[int, list] = {}
    for m in matches:
        r = m.round
        if r not in rounds_dict:
            rounds_dict[r] = []
        rounds_dict[r].append({
            "id": str(m.id),
            "match_order": m.match_order,
            "player_a_id": str(m.player_a_id) if m.player_a_id else None,
            "player_b_id": str(m.player_b_id) if m.player_b_id else None,
            "winner_id": str(m.winner_id) if m.winner_id else None,
            "status": m.status.value,
            "sets": [
                {
                    "set_number": s.set_number,
                    "score_a": s.score_a,
                    "score_b": s.score_b,
                    "tiebreak_a": s.tiebreak_a,
                    "tiebreak_b": s.tiebreak_b,
                }
                for s in sorted(m.sets, key=lambda s: s.set_number)
            ],
        })

    rounds = []
    for r in sorted(rounds_dict.keys()):
        rounds.append({
            "round": r,
            "matches": sorted(rounds_dict[r], key=lambda m: m["match_order"]),
        })

    return {"rounds": rounds}


async def get_standings(session: AsyncSession, event_id: uuid.UUID) -> list[dict]:
    """Calculate round-robin standings from confirmed matches."""
    event = await get_event_by_id(session, event_id)
    matches = await get_event_matches(session, event_id)

    # Build standings per participant
    stats: dict[uuid.UUID, dict] = {}
    for p in event.participants:
        if p.status in (EventParticipantStatus.CONFIRMED, EventParticipantStatus.REGISTERED):
            stats[p.user_id] = {
                "user_id": p.user_id,
                "nickname": p.user.nickname,
                "group_name": p.group_name or "A",
                "wins": 0,
                "losses": 0,
                "points": 0,
                "sets_won": 0,
                "sets_lost": 0,
            }

    for m in matches:
        if m.status not in (EventMatchStatus.CONFIRMED, EventMatchStatus.WALKOVER):
            continue
        if m.winner_id is None:
            continue

        loser_id = m.player_a_id if m.winner_id == m.player_b_id else m.player_b_id

        if m.winner_id in stats:
            stats[m.winner_id]["wins"] += 1
            stats[m.winner_id]["points"] += 3

        if loser_id and loser_id in stats:
            stats[loser_id]["losses"] += 1

        # Count sets won/lost
        for s in m.sets:
            if s.score_a == 0 and s.score_b == 0:
                continue  # Walkover set
            a_won = s.score_a > s.score_b
            if m.player_a_id in stats:
                stats[m.player_a_id]["sets_won"] += 1 if a_won else 0
                stats[m.player_a_id]["sets_lost"] += 0 if a_won else 1
            if m.player_b_id in stats:
                stats[m.player_b_id]["sets_won"] += 0 if a_won else 1
                stats[m.player_b_id]["sets_lost"] += 1 if a_won else 0

    # Sort by points desc, then set difference
    result = sorted(
        stats.values(),
        key=lambda s: (-s["points"], -(s["sets_won"] - s["sets_lost"])),
    )
    return result


async def cancel_event(
    session: AsyncSession,
    event: Event,
    lang: str = "en",
) -> Event:
    from app.i18n import t
    from app.services.chat import set_event_room_readonly

    if event.status == EventStatus.CANCELLED:
        raise ValueError(t("event.already_cancelled", lang))

    event.status = EventStatus.CANCELLED

    # Set chat room readonly if exists
    await set_event_room_readonly(session, event_id=event.id)

    # Notify all participants
    for p in event.participants:
        if p.status in (EventParticipantStatus.REGISTERED, EventParticipantStatus.CONFIRMED):
            await create_notification(
                session,
                recipient_id=p.user_id,
                type=NotificationType.EVENT_CANCELLED,
                actor_id=event.creator_id,
                target_type="event",
                target_id=event.id,
            )

    await session.commit()
    event = await get_event_by_id(session, event.id)
    return event
