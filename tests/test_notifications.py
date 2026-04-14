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
async def test_empty_notifications(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_empty")

    resp = await client.get("/api/v1/notifications", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_unread_count_empty(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_count0")

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"unread_count": 0}


@pytest.mark.asyncio
async def test_mark_as_read(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_read1")
    token2, uid2 = await _register_and_get_token(client, "notif_read2")

    # Follow to create a notification
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    # uid1 should have 1 unread notification
    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 1

    # Get the notification
    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notifs = resp.json()
    assert len(notifs) == 1
    assert notifs[0]["is_read"] is False
    notif_id = notifs[0]["id"]

    # Mark as read
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204

    # Unread count should be 0
    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_as_read_idempotent(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_idemp1")
    token2, uid2 = await _register_and_get_token(client, "notif_idemp2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notif_id = resp.json()[0]["id"]

    # Mark read twice — both should succeed
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token1))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_mark_as_read_wrong_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_wrong1")
    token2, uid2 = await _register_and_get_token(client, "notif_wrong2")

    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    resp = await client.get("/api/v1/notifications", headers=_auth(token1))
    notif_id = resp.json()[0]["id"]

    # uid2 tries to mark uid1's notification — should 404
    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token2))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_as_read_nonexistent(client: AsyncClient, session: AsyncSession):
    token, uid = await _register_and_get_token(client, "notif_ghost")
    fake_id = str(uuid.uuid4())

    resp = await client.patch(f"/api/v1/notifications/{fake_id}/read", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_as_read(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "notif_all1")
    token2, uid2 = await _register_and_get_token(client, "notif_all2")
    token3, uid3 = await _register_and_get_token(client, "notif_all3")

    # Two follows → two notifications for uid1
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token3))

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 2

    # Mark all read
    resp = await client.patch("/api/v1/notifications/read-all", headers=_auth(token1))
    assert resp.status_code == 204

    resp = await client.get("/api/v1/notifications/unread-count", headers=_auth(token1))
    assert resp.json()["unread_count"] == 0
