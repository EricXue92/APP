import re

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ntrp_levels_returns_all_groups(client: AsyncClient):
    """GET /api/v1/ntrp/levels returns exactly 5 level groups."""
    resp = await client.get("/api/v1/ntrp/levels")
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data
    assert len(data["groups"]) == 5


@pytest.mark.asyncio
async def test_ntrp_levels_group_structure(client: AsyncClient):
    """Each group has title, levels (non-empty), and skills list."""
    resp = await client.get("/api/v1/ntrp/levels")
    for group in resp.json()["groups"]:
        assert "title" in group
        assert "levels" in group
        assert len(group["levels"]) >= 1
        assert "skills" in group
        for level in group["levels"]:
            assert "level" in level
            assert "description" in level


@pytest.mark.asyncio
async def test_ntrp_levels_default_language_is_zh_hant(client: AsyncClient):
    """Default Accept-Language returns zh-Hant titles."""
    resp = await client.get("/api/v1/ntrp/levels")
    assert resp.status_code == 200
    first_title = resp.json()["groups"][0]["title"]
    assert "初學者" in first_title


@pytest.mark.asyncio
async def test_ntrp_levels_english(client: AsyncClient):
    """Accept-Language: en returns English titles."""
    resp = await client.get(
        "/api/v1/ntrp/levels",
        headers={"Accept-Language": "en"},
    )
    assert resp.status_code == 200
    titles = [g["title"] for g in resp.json()["groups"]]
    assert "Level 1.5 – 2.0: The Novice" in titles
    assert "Level 4.5 – 5.0: The Advanced Player" in titles


@pytest.mark.asyncio
async def test_ntrp_levels_zh_hans(client: AsyncClient):
    """Accept-Language: zh-Hans returns simplified Chinese titles."""
    resp = await client.get(
        "/api/v1/ntrp/levels",
        headers={"Accept-Language": "zh-Hans"},
    )
    assert resp.status_code == 200
    first_title = resp.json()["groups"][0]["title"]
    assert "初学者" in first_title


@pytest.mark.asyncio
async def test_ntrp_levels_valid_level_strings(client: AsyncClient):
    """Every level value matches a valid NTRP pattern like '1.5', '3.0'."""
    resp = await client.get(
        "/api/v1/ntrp/levels",
        headers={"Accept-Language": "en"},
    )
    for group in resp.json()["groups"]:
        for level in group["levels"]:
            assert re.match(r"^\d\.\d$", level["level"]), f"Bad level: {level['level']}"


@pytest.mark.asyncio
async def test_ntrp_levels_no_auth_required(client: AsyncClient):
    """Endpoint works without any Authorization header."""
    resp = await client.get("/api/v1/ntrp/levels")
    assert resp.status_code == 200
