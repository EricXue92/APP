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


from httpx import AsyncClient


async def _register_and_get_token(client: AsyncClient, username: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": "male",
            "city": "Taipei",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_register_device_endpoint(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "devapi_reg")
    resp = await client.post(
        "/api/v1/devices",
        json={"platform": "ios", "token": "fcm-endpoint-token"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["platform"] == "ios"
    assert data["token"] == "fcm-endpoint-token"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_device_duplicate_endpoint(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "devapi_dup")
    body = {"platform": "ios", "token": "fcm-dup-endpoint"}
    resp1 = await client.post("/api/v1/devices", json=body, headers=_auth(token))
    resp2 = await client.post("/api/v1/devices", json=body, headers=_auth(token))
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_delete_device_endpoint(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "devapi_del")
    await client.post(
        "/api/v1/devices",
        json={"platform": "android", "token": "fcm-delete-me"},
        headers=_auth(token),
    )
    resp = await client.delete("/api/v1/devices/fcm-delete-me", headers=_auth(token))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_device_not_found_endpoint(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "devapi_del404")
    resp = await client.delete("/api/v1/devices/nonexistent", headers=_auth(token))
    assert resp.status_code == 404
