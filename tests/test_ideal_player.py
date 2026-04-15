import uuid
from datetime import date, time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingParticipant, BookingStatus, MatchType, GenderRequirement, ParticipantStatus
from app.models.court import Court, CourtType
from app.models.notification import Notification, NotificationType
from app.models.review import Review
from app.models.user import AuthProvider
from app.services.ideal_player import evaluate_ideal_status
from app.services.user import create_user_with_auth


async def _create_user(session: AsyncSession, username: str, credit_score: int = 95) -> "User":
    user = await create_user_with_auth(
        session,
        nickname=f"Player_{username}",
        gender="male",
        city="Hong Kong",
        ntrp_level="3.5",
        language="en",
        provider=AuthProvider.USERNAME,
        provider_user_id=username,
        password="test1234",
    )
    user.credit_score = credit_score
    await session.commit()
    await session.refresh(user)
    return user


async def _create_court(session: AsyncSession) -> Court:
    court = Court(
        name="Test Court",
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.flush()
    return court


async def _seed_completed_bookings(session: AsyncSession, user_id: uuid.UUID, count: int) -> None:
    """Create `count` completed bookings with user as accepted participant."""
    court = await _create_court(session)
    for i in range(count):
        booking = Booking(
            creator_id=user_id,
            court_id=court.id,
            match_type=MatchType.SINGLES,
            play_date=date(2026, 1, 1 + i),
            start_time=time(10, 0),
            end_time=time(12, 0),
            min_ntrp="3.0",
            max_ntrp="4.0",
            gender_requirement=GenderRequirement.ANY,
            max_participants=2,
            status=BookingStatus.COMPLETED,
        )
        session.add(booking)
        await session.flush()
        participant = BookingParticipant(
            booking_id=booking.id,
            user_id=user_id,
            status=ParticipantStatus.ACCEPTED,
        )
        session.add(participant)
    await session.flush()


async def _seed_reviews(session: AsyncSession, reviewee_id: uuid.UUID, ratings: list[tuple[int, int, int]]) -> None:
    """Create reviews for user with given (skill, punctuality, sportsmanship) ratings."""
    for i, (skill, punct, sport) in enumerate(ratings):
        reviewer = await _create_user(session, f"reviewer_{reviewee_id.hex[:6]}_{i}")
        court = await _create_court(session)
        booking = Booking(
            creator_id=reviewer.id,
            court_id=court.id,
            match_type=MatchType.SINGLES,
            play_date=date(2026, 3, 1 + i),
            start_time=time(10, 0),
            end_time=time(12, 0),
            min_ntrp="3.0",
            max_ntrp="4.0",
            gender_requirement=GenderRequirement.ANY,
            max_participants=2,
            status=BookingStatus.COMPLETED,
        )
        session.add(booking)
        await session.flush()
        review = Review(
            booking_id=booking.id,
            reviewer_id=reviewer.id,
            reviewee_id=reviewee_id,
            skill_rating=skill,
            punctuality_rating=punct,
            sportsmanship_rating=sport,
        )
        session.add(review)
    await session.flush()


@pytest.mark.asyncio
async def test_not_ideal_by_default(session: AsyncSession):
    """New user with default values should not be ideal."""
    user = await _create_user(session, "default_user", credit_score=80)
    result = await evaluate_ideal_status(session, user.id)
    assert result is False
    assert user.is_ideal_player is False


@pytest.mark.asyncio
async def test_all_conditions_met(session: AsyncSession):
    """User meeting all 4 conditions becomes ideal player with GAINED notification."""
    user = await _create_user(session, "ideal_user", credit_score=95)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is True
    assert user.is_ideal_player is True

    # Check GAINED notification
    from sqlalchemy import select
    notifs = (await session.execute(
        select(Notification).where(
            Notification.recipient_id == user.id,
            Notification.type == NotificationType.IDEAL_PLAYER_GAINED,
        )
    )).scalars().all()
    assert len(notifs) == 1


@pytest.mark.asyncio
async def test_credit_score_insufficient(session: AsyncSession):
    user = await _create_user(session, "low_credit", credit_score=85)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_has_cancellations(session: AsyncSession):
    user = await _create_user(session, "cancelled_user", credit_score=95)
    user.cancel_count = 1
    await session.flush()
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_insufficient_bookings(session: AsyncSession):
    user = await _create_user(session, "few_bookings", credit_score=95)
    await _seed_completed_bookings(session, user.id, 9)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_low_review_average(session: AsyncSession):
    user = await _create_user(session, "low_reviews", credit_score=95)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(3, 3, 3)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_demotion(session: AsyncSession):
    """Already ideal player loses status when condition fails."""
    user = await _create_user(session, "demoted_user", credit_score=95)
    user.is_ideal_player = True
    await session.flush()
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    # Break a condition
    user.cancel_count = 1
    await session.flush()

    result = await evaluate_ideal_status(session, user.id)
    assert result is False
    assert user.is_ideal_player is False

    # Check LOST notification
    from sqlalchemy import select
    notifs = (await session.execute(
        select(Notification).where(
            Notification.recipient_id == user.id,
            Notification.type == NotificationType.IDEAL_PLAYER_LOST,
        )
    )).scalars().all()
    assert len(notifs) == 1


@pytest.mark.asyncio
async def test_no_change_no_notification(session: AsyncSession):
    """Re-evaluating an already-ideal user with no changes produces no new notification."""
    user = await _create_user(session, "stable_user", credit_score=95)
    user.is_ideal_player = True
    await session.flush()
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is True

    from sqlalchemy import select
    notifs = (await session.execute(
        select(Notification).where(Notification.recipient_id == user.id)
    )).scalars().all()
    assert len(notifs) == 0


from app.models.credit import CreditReason
from app.services.credit import apply_credit_change


@pytest.mark.asyncio
async def test_credit_change_triggers_evaluation(session: AsyncSession):
    """apply_credit_change should trigger ideal player evaluation."""
    user = await _create_user(session, "credit_trigger", credit_score=90)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(5, 5, 5)] * 3)

    # Attend a booking — credit goes to 95, all conditions met
    await apply_credit_change(session, user, CreditReason.ATTENDED)

    await session.refresh(user)
    assert user.is_ideal_player is True


from app.services.review import submit_review


@pytest.mark.asyncio
async def test_review_triggers_evaluation(session: AsyncSession):
    """submit_review should trigger ideal player evaluation for the reviewee."""
    reviewee = await _create_user(session, "review_target", credit_score=95)
    reviewer = await _create_user(session, "review_author", credit_score=80)
    await _seed_completed_bookings(session, reviewee.id, 10)
    # Seed reviews that bring average to >= 4.0
    await _seed_reviews(session, reviewee.id, [(5, 5, 5)] * 2)

    # Create a completed booking between reviewer and reviewee
    court = await _create_court(session)
    booking = Booking(
        creator_id=reviewer.id,
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=date(2026, 4, 1),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        gender_requirement=GenderRequirement.ANY,
        max_participants=2,
        status=BookingStatus.COMPLETED,
    )
    session.add(booking)
    await session.flush()
    for uid in [reviewer.id, reviewee.id]:
        session.add(BookingParticipant(
            booking_id=booking.id,
            user_id=uid,
            status=ParticipantStatus.ACCEPTED,
        ))
    await session.commit()

    # Submit review — this should trigger evaluation
    await submit_review(
        session,
        booking_id=booking.id,
        reviewer=reviewer,
        reviewee_id=reviewee.id,
        skill_rating=5,
        punctuality_rating=5,
        sportsmanship_rating=5,
    )

    await session.refresh(reviewee)
    assert reviewee.is_ideal_player is True


@pytest.mark.asyncio
async def test_nonexistent_user_returns_false(session: AsyncSession):
    """evaluate_ideal_status with a random UUID returns False without error."""
    result = await evaluate_ideal_status(session, uuid.uuid4())
    assert result is False


@pytest.mark.asyncio
async def test_credit_exactly_at_threshold(session: AsyncSession):
    """Credit=90 (exactly at threshold) should qualify."""
    user = await _create_user(session, "credit_90", credit_score=90)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(4, 4, 4)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is True


@pytest.mark.asyncio
async def test_credit_one_below_threshold(session: AsyncSession):
    """Credit=89 (one below threshold) should not qualify."""
    user = await _create_user(session, "credit_89", credit_score=89)
    await _seed_completed_bookings(session, user.id, 10)
    await _seed_reviews(session, user.id, [(4, 4, 4)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_avg_rating_exactly_4(session: AsyncSession):
    """Average rating of exactly 4.0 should qualify (threshold uses <, not <=)."""
    user = await _create_user(session, "rating_4_0", credit_score=95)
    await _seed_completed_bookings(session, user.id, 10)
    # (4+4+4)/3 = 4.0 exactly
    await _seed_reviews(session, user.id, [(4, 4, 4)] * 3)

    result = await evaluate_ideal_status(session, user.id)
    assert result is True


@pytest.mark.asyncio
async def test_avg_rating_below_4(session: AsyncSession):
    """Average rating of 3.99 should not qualify."""
    user = await _create_user(session, "rating_3_99", credit_score=95)
    await _seed_completed_bookings(session, user.id, 10)
    # (4+4+4)/3 * 2 reviews + (3+4+4)/3 * 1 review
    # avg = (4.0 + 4.0 + 11/3) / 3 = (4 + 4 + 3.667) / 3 = 11.667/3 ≈ 3.889 < 4.0
    await _seed_reviews(session, user.id, [(4, 4, 4), (4, 4, 4), (3, 4, 4)])

    result = await evaluate_ideal_status(session, user.id)
    assert result is False


@pytest.mark.asyncio
async def test_hidden_reviews_excluded_from_average(session: AsyncSession):
    """Hidden reviews are excluded; only visible reviews count toward average."""
    user = await _create_user(session, "hidden_review", credit_score=95)
    await _seed_completed_bookings(session, user.id, 10)

    # Add a good visible review (5,5,5) → avg per review = 5.0
    await _seed_reviews(session, user.id, [(5, 5, 5)])

    # Add a bad hidden review directly — if counted, would drag average below 4.0
    reviewer2 = await _create_user(session, "bad_reviewer_h", credit_score=80)
    court = await _create_court(session)
    bad_booking = Booking(
        creator_id=reviewer2.id,
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=date(2026, 5, 1),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        gender_requirement=GenderRequirement.ANY,
        max_participants=2,
        status=BookingStatus.COMPLETED,
    )
    session.add(bad_booking)
    await session.flush()
    hidden_review = Review(
        booking_id=bad_booking.id,
        reviewer_id=reviewer2.id,
        reviewee_id=user.id,
        skill_rating=1,
        punctuality_rating=1,
        sportsmanship_rating=1,
        is_hidden=True,
    )
    session.add(hidden_review)
    await session.flush()

    # With only the visible (5,5,5) review counting, average = 5.0 → should be ideal
    result = await evaluate_ideal_status(session, user.id)
    assert result is True
