import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.user import get_user_by_id, get_user_auth
from app.models.user import AuthProvider


async def _register_and_get_token(client: AsyncClient, username: str = "profileuser") -> str:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "ProfileTest", "gender": "male", "city": "Hong Kong", "ntrp_level": "3.5", "language": "zh-Hant"},
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_get_my_profile(client: AsyncClient):
    token = await _register_and_get_token(client)
    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["nickname"] == "ProfileTest"
    assert data["gender"] == "male"
    assert data["ntrp_level"] == "3.5"
    assert data["ntrp_label"] == "3.5 中级"
    assert data["credit_score"] == 80


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient):
    token = await _register_and_get_token(client, "updateuser")
    resp = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"nickname": "NewNickname", "ntrp_level": "4.0+", "bio": "Love tennis!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["nickname"] == "NewNickname"
    assert data["ntrp_level"] == "4.0+"
    assert data["ntrp_label"] == "4.0 中高级+"
    assert data["bio"] == "Love tennis!"


@pytest.mark.asyncio
async def test_get_profile_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_profile_invalid_token(client: AsyncClient):
    resp = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer invalid.token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_user_by_id_found(client: AsyncClient, session: AsyncSession):
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "FindMe", "gender": "male", "city": "HK", "ntrp_level": "3.5", "language": "en"},
        json={"username": "findme", "password": "pass1234", "email": "find@test.com"},
    )
    user_id = uuid.UUID(resp.json()["user_id"])
    user = await get_user_by_id(session, user_id)
    assert user is not None
    assert user.id == user_id


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(session: AsyncSession):
    user = await get_user_by_id(session, uuid.uuid4())
    assert user is None


@pytest.mark.asyncio
async def test_get_user_auth_not_found(session: AsyncSession):
    auth = await get_user_auth(session, AuthProvider.USERNAME, "nonexistent_user")
    assert auth is None


@pytest.mark.asyncio
async def test_patch_me_empty_body(client: AsyncClient, session: AsyncSession):
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "EmptyPatch", "gender": "male", "city": "HK", "ntrp_level": "3.5", "language": "en"},
        json={"username": "emptypatch", "password": "pass1234", "email": "ep@test.com"},
    )
    token = resp.json()["access_token"]

    resp = await client.patch("/api/v1/users/me", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_me_individual_fields(client: AsyncClient, session: AsyncSession):
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "FieldPatch", "gender": "male", "city": "HK", "ntrp_level": "3.5", "language": "en"},
        json={"username": "fieldpatch", "password": "pass1234", "email": "fp@test.com"},
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Update city only
    resp = await client.patch("/api/v1/users/me", json={"city": "Taipei"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["city"] == "Taipei"

    # Update years_playing only
    resp = await client.patch("/api/v1/users/me", json={"years_playing": 5}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["years_playing"] == 5
