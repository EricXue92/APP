import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_register_username(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "TestPlayer",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": "testuser", "password": "secure123", "email": "test@example.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "Player1", "gender": "female", "city": "Hong Kong", "ntrp_level": "3.0", "language": "zh-Hant"},
        json={"username": "duplicate", "password": "secure123", "email": "dup@example.com"},
    )
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "Player2", "gender": "male", "city": "Hong Kong", "ntrp_level": "4.0", "language": "zh-Hant"},
        json={"username": "duplicate", "password": "other123", "email": "dup2@example.com"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_username(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "LoginTest", "gender": "male", "city": "Hong Kong", "ntrp_level": "3.5", "language": "en"},
        json={"username": "loginuser", "password": "mypassword", "email": "login@example.com"},
    )
    resp = await client.post("/api/v1/auth/login/username", json={"username": "loginuser", "password": "mypassword"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "WrongPw", "gender": "female", "city": "Hong Kong", "ntrp_level": "2.5", "language": "zh-Hant"},
        json={"username": "wrongpw", "password": "correct123", "email": "wp@example.com"},
    )
    resp = await client.post("/api/v1/auth/login/username", json={"username": "wrongpw", "password": "wrong999"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    reg = await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": "RefreshTest", "gender": "male", "city": "Hong Kong", "ntrp_level": "4.0", "language": "en"},
        json={"username": "refreshuser", "password": "pass1234", "email": "ref@example.com"},
    )
    refresh_token = reg.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
