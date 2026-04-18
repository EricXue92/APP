import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.stats import UserStats
from app.schemas.user import UserProfileResponse, UserUpdateRequest
from app.services.block import is_blocked
from app.services.stats import get_user_stats
from app.services.user import update_user

router = APIRouter()


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
