import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DbSession, Lang
from app.models.review import Review
from app.schemas.review import PendingReviewItem, ReviewCreateRequest, ReviewResponse, UserReviewSummary
from app.services.review import (
    get_booking_reviews_for_user,
    get_pending_reviews,
    get_review_averages,
    get_revealed_reviews_for_user,
    submit_review,
)

router = APIRouter()


def _review_to_response(review, is_revealed: bool) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        booking_id=review.booking_id,
        reviewer_id=review.reviewer_id,
        reviewee_id=review.reviewee_id,
        reviewer_nickname=review.reviewer.nickname,
        skill_rating=review.skill_rating,
        punctuality_rating=review.punctuality_rating,
        sportsmanship_rating=review.sportsmanship_rating,
        comment=review.comment,
        is_revealed=is_revealed,
        created_at=review.created_at,
    )


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(body: ReviewCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        review, is_revealed = await submit_review(
            session,
            booking_id=body.booking_id,
            reviewer=user,
            reviewee_id=body.reviewee_id,
            skill_rating=body.skill_rating,
            punctuality_rating=body.punctuality_rating,
            sportsmanship_rating=body.sportsmanship_rating,
            comment=body.comment,
            lang=lang,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # Reload review with reviewer relationship
    result = await session.execute(
        select(Review)
        .options(selectinload(Review.reviewer))
        .where(Review.id == review.id)
    )
    review = result.scalar_one()

    return _review_to_response(review, is_revealed)


@router.get("/pending", response_model=list[PendingReviewItem])
async def list_pending_reviews(user: CurrentUser, session: DbSession):
    items = await get_pending_reviews(session, user.id)
    return items


@router.get("/users/{user_id}", response_model=UserReviewSummary)
async def get_user_reviews(user_id: str, session: DbSession):
    uid = uuid.UUID(user_id)
    reviews = await get_revealed_reviews_for_user(session, uid)
    averages = await get_review_averages(session, uid)

    review_responses = [
        _review_to_response(r, is_revealed=True) for r in reviews
    ]

    return UserReviewSummary(
        average_skill=averages["average_skill"],
        average_punctuality=averages["average_punctuality"],
        average_sportsmanship=averages["average_sportsmanship"],
        total_reviews=averages["total_reviews"],
        reviews=review_responses,
    )


@router.get("/bookings/{booking_id}", response_model=list[ReviewResponse])
async def get_booking_reviews(booking_id: str, user: CurrentUser, session: DbSession):
    items = await get_booking_reviews_for_user(session, uuid.UUID(booking_id), user.id)
    return [_review_to_response(item["review"], item["is_revealed"]) for item in items]
