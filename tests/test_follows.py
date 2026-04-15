import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.services.follow import is_mutual, remove_follows_between


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
    # One-way follows — is_mutual must be False
    assert all(d["is_mutual"] is False for d in data)


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


@pytest.mark.asyncio
async def test_follow_self_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "selffollow")

    resp = await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_follow_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "dupfol1")
    token2, uid2 = await _register_and_get_token(client, "dupfol2")

    await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    resp = await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unfollow_nonexistent(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "unfolghost")
    fake_id = str(uuid.uuid4())

    resp = await client.delete(f"/api/v1/follows/{fake_id}", headers=_auth(token1))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_follow_nonexistent_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "folghost")
    fake_id = str(uuid.uuid4())

    resp = await client.post("/api/v1/follows", json={"followed_id": fake_id}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_follow_blocked_user_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "blkfol1")
    token2, uid2 = await _register_and_get_token(client, "blkfol2")

    # Block user2
    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    # Try to follow blocked user
    resp = await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_follow_user_who_blocked_you_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "blkrev1")
    token2, uid2 = await _register_and_get_token(client, "blkrev2")

    # User2 blocks user1
    await client.post("/api/v1/blocks", json={"blocked_id": uid1}, headers=_auth(token2))

    # User1 tries to follow user2 — should fail
    resp = await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_follows_removed_on_block(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "folblk1")
    token2, uid2 = await _register_and_get_token(client, "folblk2")

    # Create mutual follow
    await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    # Verify both following
    resp = await client.get("/api/v1/follows/following", headers=_auth(token1))
    assert len(resp.json()) == 1
    resp = await client.get("/api/v1/follows/following", headers=_auth(token2))
    assert len(resp.json()) == 1

    # User1 blocks user2
    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    # Both follow lists should be empty
    resp = await client.get("/api/v1/follows/following", headers=_auth(token1))
    assert len(resp.json()) == 0
    resp = await client.get("/api/v1/follows/following", headers=_auth(token2))
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_cannot_follow_while_blocked(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "nofol1")
    token2, uid2 = await _register_and_get_token(client, "nofol2")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    # Neither can follow the other
    resp = await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 400
    resp = await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_is_mutual_direct(client: AsyncClient, session: AsyncSession):
    """Direct unit test of is_mutual() service function."""
    token1, uid1 = await _register_and_get_token(client, "ismut1")
    token2, uid2 = await _register_and_get_token(client, "ismut2")
    uid1 = uuid.UUID(uid1)
    uid2 = uuid.UUID(uid2)

    # A follows B — not mutual yet
    await client.post("/api/v1/follows", json={"followed_id": str(uid2)}, headers=_auth(token1))
    assert await is_mutual(session, uid1, uid2) is False

    # B follows A — now mutual
    await client.post("/api/v1/follows", json={"followed_id": str(uid1)}, headers=_auth(token2))
    assert await is_mutual(session, uid1, uid2) is True
    assert await is_mutual(session, uid2, uid1) is True


@pytest.mark.asyncio
async def test_remove_follows_between_direct(client: AsyncClient, session: AsyncSession):
    """Direct unit test of remove_follows_between() service function."""
    token1, uid1 = await _register_and_get_token(client, "rmfol1")
    token2, uid2 = await _register_and_get_token(client, "rmfol2")
    uid1 = uuid.UUID(uid1)
    uid2 = uuid.UUID(uid2)

    # Create follows in both directions
    await client.post("/api/v1/follows", json={"followed_id": str(uid2)}, headers=_auth(token1))
    await client.post("/api/v1/follows", json={"followed_id": str(uid1)}, headers=_auth(token2))

    # Verify both exist before removal
    assert await is_mutual(session, uid1, uid2) is True

    # Call service function directly
    await remove_follows_between(session, uid1, uid2)
    await session.commit()

    # Both directions should be gone
    assert await is_mutual(session, uid1, uid2) is False

    # Verify via API as well
    resp = await client.get("/api/v1/follows/following", headers=_auth(token1))
    assert len(resp.json()) == 0
    resp = await client.get("/api/v1/follows/following", headers=_auth(token2))
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_empty_followers_list(client: AsyncClient, session: AsyncSession):
    """User with no followers returns an empty list."""
    token1, uid1 = await _register_and_get_token(client, "nofans1")

    resp = await client.get("/api/v1/follows/followers", headers=_auth(token1))
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.get("/api/v1/follows/following", headers=_auth(token1))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_follow_unfollow_refollow(client: AsyncClient, session: AsyncSession):
    """Follow → unfollow → re-follow works and mutual status resets correctly."""
    token1, uid1 = await _register_and_get_token(client, "refollow1")
    token2, uid2 = await _register_and_get_token(client, "refollow2")

    # A follows B
    resp = await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201

    # B follows A — mutual
    await client.post("/api/v1/follows", json={"followed_id": uid1}, headers=_auth(token2))

    # A unfollows B — breaks mutual
    resp = await client.delete(f"/api/v1/follows/{uid2}", headers=_auth(token1))
    assert resp.status_code == 204

    # Verify B's follow of A is now one-way
    resp = await client.get("/api/v1/follows/following", headers=_auth(token2))
    assert resp.json()[0]["is_mutual"] is False

    # A re-follows B — mutual again
    resp = await client.post("/api/v1/follows", json={"followed_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201
    assert resp.json()["is_mutual"] is True

    # Verify mutual is restored in list view
    resp = await client.get("/api/v1/follows/following", headers=_auth(token2))
    assert resp.json()[0]["is_mutual"] is True


@pytest.mark.asyncio
async def test_mutual_follow_notifications(client: AsyncClient, session: AsyncSession):
    """When B follows A (making it mutual), both NEW_FOLLOWER and NEW_MUTUAL notifications exist."""
    token1, uid1 = await _register_and_get_token(client, "mutnot1")
    token2, uid2 = await _register_and_get_token(client, "mutnot2")
    uid1 = uuid.UUID(uid1)
    uid2 = uuid.UUID(uid2)

    # A follows B — B gets a NEW_FOLLOWER notification
    await client.post("/api/v1/follows", json={"followed_id": str(uid2)}, headers=_auth(token1))

    result = await session.execute(
        select(Notification).where(
            Notification.recipient_id == uid2,
            Notification.type == NotificationType.NEW_FOLLOWER,
        )
    )
    assert result.scalar_one_or_none() is not None

    # B follows A — A gets NEW_FOLLOWER + NEW_MUTUAL (because it's now mutual)
    await client.post("/api/v1/follows", json={"followed_id": str(uid1)}, headers=_auth(token2))

    result = await session.execute(
        select(Notification).where(
            Notification.recipient_id == uid1,
            Notification.type == NotificationType.NEW_FOLLOWER,
        )
    )
    assert result.scalar_one_or_none() is not None, "NEW_FOLLOWER notification missing for uid1"

    result = await session.execute(
        select(Notification).where(
            Notification.recipient_id == uid1,
            Notification.type == NotificationType.NEW_MUTUAL,
        )
    )
    assert result.scalar_one_or_none() is not None, "NEW_MUTUAL notification missing for uid1"
