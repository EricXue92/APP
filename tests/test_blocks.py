import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType


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
async def test_block_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "blocker1")
    token2, uid2 = await _register_and_get_token(client, "blocked1")

    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201
    data = resp.json()
    assert data["blocker_id"] == uid1
    assert data["blocked_id"] == uid2


@pytest.mark.asyncio
async def test_block_self_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "selfblocker")

    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid1}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_block_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "dupblocker")
    token2, uid2 = await _register_and_get_token(client, "dupblocked")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unblock_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "unblocker")
    token2, uid2 = await _register_and_get_token(client, "unblocked")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    resp = await client.delete(f"/api/v1/blocks/{uid2}", headers=_auth(token1))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_unblock_nonexistent(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "unblocker2")
    fake_id = str(uuid.uuid4())

    resp = await client.delete(f"/api/v1/blocks/{fake_id}", headers=_auth(token1))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_blocks(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "lister1")
    token2, uid2 = await _register_and_get_token(client, "listed1")
    token3, uid3 = await _register_and_get_token(client, "listed2")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    await client.post("/api/v1/blocks", json={"blocked_id": uid3}, headers=_auth(token1))

    resp = await client.get("/api/v1/blocks", headers=_auth(token1))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
