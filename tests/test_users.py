import pytest
from httpx import AsyncClient


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
