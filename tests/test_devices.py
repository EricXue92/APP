import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_token import DeviceToken


@pytest.mark.asyncio
async def test_create_device_token(session: AsyncSession):
    from app.models.user import User, Gender

    user = User(nickname="push_user", gender=Gender.MALE, city="Taipei", ntrp_level="3.5", ntrp_label="3.5")
    session.add(user)
    await session.flush()

    token = DeviceToken(user_id=user.id, platform="ios", token="fcm-token-abc123")
    session.add(token)
    await session.flush()

    result = await session.execute(select(DeviceToken).where(DeviceToken.user_id == user.id))
    saved = result.scalar_one()
    assert saved.platform == "ios"
    assert saved.token == "fcm-token-abc123"
    assert saved.id is not None
    assert saved.created_at is not None
