import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_token import DeviceToken


async def register_device(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    platform: str,
    token: str,
) -> DeviceToken:
    result = await session.execute(
        select(DeviceToken).where(
            DeviceToken.user_id == user_id,
            DeviceToken.token == token,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    device_token = DeviceToken(user_id=user_id, platform=platform, token=token)
    session.add(device_token)
    await session.flush()
    return device_token


async def remove_device(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    token: str,
) -> None:
    result = await session.execute(
        select(DeviceToken).where(
            DeviceToken.user_id == user_id,
            DeviceToken.token == token,
        )
    )
    device_token = result.scalar_one_or_none()
    if device_token is None:
        raise LookupError("Device token not found")
    await session.delete(device_token)
    await session.flush()


async def get_user_device_tokens(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[DeviceToken]:
    result = await session.execute(
        select(DeviceToken).where(DeviceToken.user_id == user_id)
    )
    return list(result.scalars().all())
