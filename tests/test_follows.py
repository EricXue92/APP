import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _register_and_get_token(client: AsyncClient, username: str, gender: str = "male", ntrp: str = "3.5") -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": gender,
            "city": "Hong Kong",
            "ntrp_level": ntrp,
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_follow_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "follower1")
    token2, uid2 = await _register_and_get_token(client, "followed1")

    resp = await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201
    data = resp.json()
    assert data["follower_id"] == uid1
    assert data["followed_id"] == uid2
    assert data["is_mutual"] is False


@pytest.mark.asyncio
async def test_unfollow_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "unfollower1")
    token2, uid2 = await _register_and_get_token(client, "unfollowed1")

    await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    resp = await client.delete(f"/api/v1/follows/{uid2}", headers=_auth(token1))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_list_followers(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "popular1")
    token2, uid2 = await _register_and_get_token(client, "fan1")
    token3, uid3 = await _register_and_get_token(client, "fan2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token3))

    resp = await client.get("/api/v1/follows/followers", headers=_auth(token1))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_following(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "fan3")
    token2, uid2 = await _register_and_get_token(client, "celeb1")
    token3, uid3 = await _register_and_get_token(client, "celeb2")

    await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    await client.post("/api/v1/follows", json={"followed_id": uid3}, headers=_auth(token1))

    resp = await client.get("/api/v1/follows/following", headers=_auth(token1))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_mutual_follow(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "mutual1")
    token2, uid2 = await _register_and_get_token(client, "mutual2")

    # A follows B — not mutual yet
    resp = await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201
    assert resp.json()["is_mutual"] is False

    # B follows A — now mutual
    resp = await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))
    assert resp.status_code == 201
    assert resp.json()["is_mutual"] is True

    # Verify both show as mutual in followers list
    resp = await client.get("/api/v1/follows/followers", headers=_auth(token1))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_mutual"] is True


@pytest.mark.asyncio
async def test_mutual_broken_on_unfollow(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "breakmut1")
    token2, uid2 = await _register_and_get_token(client, "breakmut2")

    # Create mutual follow
    await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    # A unfollows B
    await client.delete(f"/api/v1/follows/{uid2}", headers=_auth(token1))

    # B's follow of A should no longer be mutual
    resp = await client.get("/api/v1/follows/following", headers=_auth(token2))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_mutual"] is False
