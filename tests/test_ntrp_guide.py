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
