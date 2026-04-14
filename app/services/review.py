import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.i18n import t
from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.review import Review
from app.models.user import User

REVIEW_WINDOW_HOURS = 24


def _reverse_review_exists_clause():
    """Correlated EXISTS subquery: does the reverse review exist for a given Review row?"""
    reverse = Review.__table__.alias("reverse_review")
    return exists(
        select(reverse.c.id).where(
            and_(
                reverse.c.booking_id == Review.booking_id,
                reverse.c.reviewer_id == Review.reviewee_id,
                reverse.c.reviewee_id == Review.reviewer_id,
            )
        )
    )


async def submit_review(
    session: AsyncSession,
    *,
    booking_id: uuid.UUID,
    reviewer: User,
    reviewee_id: uuid.UUID,
    skill_rating: int,
    punctuality_rating: int,
    sportsmanship_rating: int,
    comment: str | None = None,
    lang: str = "en",
) -> tuple[Review, bool]:
    """Submit a review. Returns (review, is_revealed)."""
    # Load booking with participants
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.participants))
        .where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if booking is None:
        raise ValueError(t("booking.not_found", lang))

    # Booking must be completed
    if booking.status != BookingStatus.COMPLETED:
        raise ValueError(t("review.booking_not_completed", lang))

    # Cannot review self
    if reviewer.id == reviewee_id:
        raise ValueError(t("review.cannot_review_self", lang))

    # Both must be accepted participants
    participant_ids = {
        p.user_id for p in booking.participants if p.status == ParticipantStatus.ACCEPTED
    }
    if reviewer.id not in participant_ids:
        raise PermissionError(t("review.not_participant", lang))
    if reviewee_id not in participant_ids:
        raise PermissionError(t("review.not_participant", lang))

    # Within 24h window
    now = datetime.now(timezone.utc)
    window_end = booking.updated_at.replace(tzinfo=timezone.utc) if booking.updated_at.tzinfo is None else booking.updated_at
    if now > window_end + timedelta(hours=REVIEW_WINDOW_HOURS):
        raise ValueError(t("review.window_expired", lang))

    # Check duplicate
    dup_result = await session.execute(
        select(Review).where(
            Review.booking_id == booking_id,
            Review.reviewer_id == reviewer.id,
            Review.reviewee_id == reviewee_id,
        )
    )
    if dup_result.scalar_one_or_none() is not None:
        raise LookupError(t("review.already_submitted", lang))

    # Create review
    review = Review(
        booking_id=booking_id,
        reviewer_id=reviewer.id,
        reviewee_id=reviewee_id,
        skill_rating=skill_rating,
        punctuality_rating=punctuality_rating,
        sportsmanship_rating=sportsmanship_rating,
        comment=comment,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)

    # Check if reverse review exists (is_revealed)
    reverse = await get_reverse_review(session, booking_id, reviewer.id, reviewee_id)
    is_revealed = reverse is not None

    return review, is_revealed


async def get_reverse_review(
    session: AsyncSession,
    booking_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    reviewee_id: uuid.UUID,
) -> Review | None:
    """Check if reviewee has reviewed reviewer for the same booking."""
    result = await session.execute(
        select(Review).where(
            Review.booking_id == booking_id,
            Review.reviewer_id == reviewee_id,
            Review.reviewee_id == reviewer_id,
        )
    )
    return result.scalar_one_or_none()


async def get_revealed_reviews_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[Review]:
    """Get reviews where user is reviewee, not hidden, and reverse review exists."""
    result = await session.execute(
        select(Review)
        .options(selectinload(Review.reviewer))
        .where(
            Review.reviewee_id == user_id,
            Review.is_hidden == False,  # noqa: E712
            _reverse_review_exists_clause(),
        )
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


async def get_review_averages(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Return average ratings and count for revealed reviews."""
    result = await session.execute(
        select(
            func.avg(Review.skill_rating),
            func.avg(Review.punctuality_rating),
            func.avg(Review.sportsmanship_rating),
            func.count(Review.id),
        ).where(
            Review.reviewee_id == user_id,
            Review.is_hidden == False,  # noqa: E712
            _reverse_review_exists_clause(),
        )
    )
    row = result.one()
    count = row[3]
    if count == 0:
        return {
            "average_skill": 0.0,
            "average_punctuality": 0.0,
            "average_sportsmanship": 0.0,
            "total_reviews": 0,
        }
    return {
        "average_skill": round(float(row[0]), 1),
        "average_punctuality": round(float(row[1]), 1),
        "average_sportsmanship": round(float(row[2]), 1),
        "total_reviews": count,
    }


async def get_booking_reviews_for_user(
    session: AsyncSession,
    booking_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[dict]:
    """Return reviews for a booking visible to the given user.

    - Reviews where user is reviewer are always visible (is_revealed depends on reverse).
    - Reviews where user is reviewee are only visible if reverse review exists.
    """
    # Get all reviews for this booking involving this user
    result = await session.execute(
        select(Review)
        .options(selectinload(Review.reviewer))
        .where(
            Review.booking_id == booking_id,
            (Review.reviewer_id == user_id) | (Review.reviewee_id == user_id),
        )
    )
    reviews = list(result.scalars().all())

    items = []
    for review in reviews:
        if review.reviewer_id == user_id:
            # User wrote this review — always visible
            reverse = await get_reverse_review(session, booking_id, review.reviewer_id, review.reviewee_id)
            items.append({"review": review, "is_revealed": reverse is not None})
        elif review.reviewee_id == user_id:
            # Review about the user — only visible if user also reviewed the reviewer
            reverse = await get_reverse_review(session, booking_id, review.reviewer_id, review.reviewee_id)
            if reverse is not None:
                items.append({"review": review, "is_revealed": True})

    return items


async def get_pending_reviews(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[dict]:
    """Get completed bookings within 24h window where user has unreviewed co-participants."""
    now = datetime.now(timezone.utc)

    # Find completed bookings where user is accepted participant and within 24h window
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.participants).selectinload(BookingParticipant.user),
            selectinload(Booking.court),
        )
        .join(BookingParticipant)
        .where(
            Booking.status == BookingStatus.COMPLETED,
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
        )
    )
    bookings = list(result.scalars().all())

    pending = []
    for booking in bookings:
        # Check 24h window
        updated = booking.updated_at.replace(tzinfo=timezone.utc) if booking.updated_at.tzinfo is None else booking.updated_at
        if now > updated + timedelta(hours=REVIEW_WINDOW_HOURS):
            continue

        # Find accepted co-participants not yet reviewed
        accepted_participants = [
            p for p in booking.participants
            if p.status == ParticipantStatus.ACCEPTED and p.user_id != user_id
        ]

        # Batch query: which co-participants have already been reviewed?
        submitted_result = await session.execute(
            select(Review.reviewee_id).where(
                Review.booking_id == booking.id,
                Review.reviewer_id == user_id,
            )
        )
        already_reviewed = set(submitted_result.scalars().all())

        reviewees = []
        for p in accepted_participants:
            if p.user_id not in already_reviewed:
                reviewees.append({
                    "user_id": str(p.user_id),
                    "nickname": p.user.nickname,
                })

        if reviewees:
            pending.append({
                "booking_id": str(booking.id),
                "court_name": booking.court.name,
                "play_date": booking.play_date.isoformat(),
                "reviewees": reviewees,
                "window_closes_at": updated + timedelta(hours=REVIEW_WINDOW_HOURS),
            })

    return pending
