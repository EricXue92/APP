from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession
from app.schemas.user import UserProfileResponse, UserUpdateRequest
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
