import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.stats import UserCalendar, UserStats
from app.schemas.user import UserProfileResponse, UserUpdateRequest
from app.schemas.user_search import UserSearchResponse
from app.services.block import is_blocked
from app.services.stats import get_user_calendar, get_user_stats
from app.services.user import update_user
from app.services.user_search import search_users

router = APIRouter()


@router.get("/search", response_model=UserSearchResponse)
async def search(
    session: DbSession,
    user: CurrentUser,
    keyword: str | None = Query(default=None, max_length=50),
    city: str | None = Query(default=None, max_length=50),
    gender: str | None = Query(default=None, pattern=r"^(male|female)$"),
    min_ntrp: str | None = Query(default=None, pattern=r"^\d\.\d[+-]?$"),
    max_ntrp: str | None = Query(default=None, pattern=r"^\d\.\d[+-]?$"),
    court_id: uuid.UUID | None = Query(default=None),
    radius_km: float = Query(default=10.0, ge=1.0, le=50.0),
    ideal_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
):
    result = await search_users(
        session,
        caller_id=user.id,
        keyword=keyword,
        city=city,
        gender=gender,
        min_ntrp=min_ntrp,
        max_ntrp=max_ntrp,
        court_id=court_id,
        radius_km=radius_km,
        ideal_only=ideal_only,
        page=page,
        page_size=page_size,
    )
    return result


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(body: UserUpdateRequest, user: CurrentUser, session: DbSession):
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return user
    updated = await update_user(session, user, **update_data)
    return updated


@router.get("/{user_id}/stats", response_model=UserStats)
async def get_stats(user_id: uuid.UUID, user: CurrentUser, session: DbSession):
    if await is_blocked(session, user.id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    result = await get_user_stats(session, user_id)
    return result


@router.get("/{user_id}/calendar", response_model=UserCalendar)
async def get_calendar(
    user_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    if await is_blocked(session, user.id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    result = await get_user_calendar(session, user_id, year, month)
    return result
