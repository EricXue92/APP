import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.schemas.follow import FollowCreateRequest, FollowResponse
from app.services.follow import create_follow, delete_follow, list_followers, list_following

router = APIRouter()


@router.post("", response_model=FollowResponse, status_code=status.HTTP_201_CREATED)
async def follow_user(body: FollowCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        result = await create_follow(session, follower_id=user.id, followed_id=body.followed_id, lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return result


@router.delete("/{followed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(followed_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        await delete_follow(session, follower_id=user.id, followed_id=uuid.UUID(followed_id), lang=lang)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/followers", response_model=list[FollowResponse])
async def get_my_followers(user: CurrentUser, session: DbSession):
    return await list_followers(session, user.id)


@router.get("/following", response_model=list[FollowResponse])
async def get_my_following(user: CurrentUser, session: DbSession):
    return await list_following(session, user.id)
