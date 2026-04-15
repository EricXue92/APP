import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_token import DeviceToken, Platform


@pytest.mark.asyncio
async def test_create_device_token(session: AsyncSession):
    from app.models.user import User, Gender

    user = User(nickname="push_user", gender=Gender.MALE, city="Taipei", ntrp_level="3.5", ntrp_label="3.5")
    session.add(user)
    await session.flush()

    token = DeviceToken(user_id=user.id, platform=Platform.IOS, token="fcm-token-abc123")
    session.add(token)
    await session.flush()

    result = await session.execute(select(DeviceToken).where(DeviceToken.user_id == user.id))
    saved = result.scalar_one()
    assert saved.platform == Platform.IOS
    assert saved.token == "fcm-token-abc123"
    assert saved.id is not None
    assert saved.created_at is not None


from app.services.device import register_device, remove_device, get_user_device_tokens


async def _create_user(session: AsyncSession, username: str) -> uuid.UUID:
    from app.models.user import User, Gender

    user = User(nickname=f"Player_{username}", gender=Gender.MALE, city="Taipei", ntrp_level="3.5", ntrp_label="3.5")
    session.add(user)
    await session.flush()
    return user.id


@pytest.mark.asyncio
async def test_register_device(session: AsyncSession):
    user_id = await _create_user(session, "dev_reg")
    dt = await register_device(session, user_id=user_id, platform="android", token="fcm-token-111")
    assert dt.user_id == user_id
    assert dt.platform == "android"
    assert dt.token == "fcm-token-111"


@pytest.mark.asyncio
async def test_register_device_duplicate_is_idempotent(session: AsyncSession):
    user_id = await _create_user(session, "dev_dup")
    dt1 = await register_device(session, user_id=user_id, platform="ios", token="fcm-dup-token")
    dt2 = await register_device(session, user_id=user_id, platform="ios", token="fcm-dup-token")
    assert dt1.id == dt2.id

    tokens = await get_user_device_tokens(session, user_id)
    assert len(tokens) == 1


@pytest.mark.asyncio
async def test_multiple_devices_per_user(session: AsyncSession):
    user_id = await _create_user(session, "dev_multi")
    await register_device(session, user_id=user_id, platform="ios", token="token-iphone")
    await register_device(session, user_id=user_id, platform="android", token="token-android")

    tokens = await get_user_device_tokens(session, user_id)
    assert len(tokens) == 2


@pytest.mark.asyncio
async def test_remove_device(session: AsyncSession):
    user_id = await _create_user(session, "dev_rm")
    await register_device(session, user_id=user_id, platform="ios", token="token-remove-me")
    await remove_device(session, user_id=user_id, token="token-remove-me")

    tokens = await get_user_device_tokens(session, user_id)
    assert len(tokens) == 0


@pytest.mark.asyncio
async def test_remove_device_not_found(session: AsyncSession):
    user_id = await _create_user(session, "dev_rm404")
    with pytest.raises(LookupError):
        await remove_device(session, user_id=user_id, token="nonexistent-token")
