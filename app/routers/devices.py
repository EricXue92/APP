from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.device import DeviceTokenCreate, DeviceTokenResponse
from app.services.device import register_device, remove_device

router = APIRouter()


@router.post("", response_model=DeviceTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_device_token(body: DeviceTokenCreate, user: CurrentUser, session: DbSession):
    dt = await register_device(session, user_id=user.id, platform=body.platform, token=body.token)
    await session.commit()
    return dt


@router.delete("/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_token(token: str, user: CurrentUser, session: DbSession):
    try:
        await remove_device(session, user_id=user.id, token=token)
        await session.commit()
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device token not found")
