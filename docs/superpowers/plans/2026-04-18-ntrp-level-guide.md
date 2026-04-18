# NTRP Level Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public, trilingual reference endpoint that returns standard NTRP level descriptions so users can self-identify their level.

**Architecture:** Pure read-only content delivery — no database, no auth. Trilingual text hardcoded in a service dict (matching the app's existing i18n pattern). Router delegates to service, service resolves language and returns structured groups.

**Tech Stack:** FastAPI, Pydantic v2

---

## File Structure

| Action | File                         | Responsibility                                             |
| ------ | ---------------------------- | ---------------------------------------------------------- |
| Create | `app/services/ntrp_guide.py` | Trilingual content data + `get_level_guide(lang)` resolver |
| Create | `app/schemas/ntrp_guide.py`  | Pydantic response models                                   |
| Create | `app/routers/ntrp_guide.py`  | `GET /levels` endpoint                                     |
| Modify | `app/main.py:27,30-46`       | Register router                                            |
| Create | `tests/test_ntrp_guide.py`   | Integration tests                                          |

---

### Task 1: Schemas

**Files:**

- Create: `app/schemas/ntrp_guide.py`
- Test: `tests/test_ntrp_guide.py`

- [ ] **Step 1: Write schema tests**

Create `tests/test_ntrp_guide.py` with schema validation tests:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ntrp_guide.py -v`
Expected: FAIL — endpoint does not exist yet (404 or import error).

- [ ] **Step 3: Create schema file**

Create `app/schemas/ntrp_guide.py`:

```python
from pydantic import BaseModel


class SkillNote(BaseModel):
    name: str
    description: str

    model_config = {"from_attributes": True}


class LevelDetail(BaseModel):
    level: str
    description: str

    model_config = {"from_attributes": True}


class LevelGroup(BaseModel):
    title: str
    levels: list[LevelDetail]
    skills: list[SkillNote]

    model_config = {"from_attributes": True}


class LevelGuideResponse(BaseModel):
    groups: list[LevelGroup]

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Commit**

```bash
git add app/schemas/ntrp_guide.py tests/test_ntrp_guide.py
git commit -m "feat(ntrp): add schemas and initial tests for level guide"
```

---

### Task 2: Service Layer

**Files:**

- Create: `app/services/ntrp_guide.py`

- [ ] **Step 1: Create service with trilingual content**

Create `app/services/ntrp_guide.py`:

```python
LEVEL_GROUPS = [
    {
        "title": {
            "en": "Level 1.5 – 2.0: The Novice",
            "zh-Hant": "等級 1.5 – 2.0：初學者",
            "zh-Hans": "等级 1.5 – 2.0：初学者",
        },
        "levels": [
            {
                "level": "1.5",
                "description": {
                    "en": "You are just starting to play. You are working on making contact with the ball and learning the basic court lines.",
                    "zh-Hant": "你剛開始打網球，正在學習擊球和熟悉基本的場地線。",
                    "zh-Hans": "你刚开始打网球，正在学习击球和熟悉基本的场地线。",
                },
            },
            {
                "level": "2.0",
                "description": {
                    "en": "You can sustain a short rally at a slow pace. You are familiar with the basic positions for singles and doubles play.",
                    "zh-Hant": "你能以較慢的節奏維持短暫的對打，並熟悉單打和雙打的基本站位。",
                    "zh-Hans": "你能以较慢的节奏维持短暂的对打，并熟悉单打和双打的基本站位。",
                },
            },
        ],
        "skills": [
            {
                "name": {
                    "en": "Forehand",
                    "zh-Hant": "正手",
                    "zh-Hans": "正手",
                },
                "description": {
                    "en": "Developing a consistent swing.",
                    "zh-Hant": "正在培養穩定的揮拍動作。",
                    "zh-Hans": "正在培养稳定的挥拍动作。",
                },
            },
            {
                "name": {
                    "en": "Backhand",
                    "zh-Hant": "反手",
                    "zh-Hans": "反手",
                },
                "description": {
                    "en": "Avoids using the backhand; grip issues are common.",
                    "zh-Hant": "傾向避開反手擊球；握拍方式常有問題。",
                    "zh-Hans": "倾向避开反手击球；握拍方式常有问题。",
                },
            },
            {
                "name": {
                    "en": "Serve/Return",
                    "zh-Hant": "發球/接發球",
                    "zh-Hans": "发球/接发球",
                },
                "description": {
                    "en": "Can get the ball in play, though double faults are frequent.",
                    "zh-Hant": "能把球發進場內，但雙發失誤頻繁。",
                    "zh-Hans": "能把球发进场内，但双发失误频繁。",
                },
            },
        ],
    },
    {
        "title": {
            "en": "Level 2.5 – 3.0: The Intermediate Beginner",
            "zh-Hant": "等級 2.5 – 3.0：進階初學者",
            "zh-Hans": "等级 2.5 – 3.0：进阶初学者",
        },
        "levels": [
            {
                "level": "2.5",
                "description": {
                    "en": "You can judge where the ball is going, but movement is still a bit mechanical. You can sustain a short rally with others of the same ability.",
                    "zh-Hant": "你能判斷球的走向，但移動仍較為僵硬。你可以與同等水平的人維持短暫的對打。",
                    "zh-Hans": "你能判断球的走向，但移动仍较为僵硬。你可以与同等水平的人维持短暂的对打。",
                },
            },
            {
                "level": "3.0",
                "description": {
                    "en": "This is the most common starting point for league play. You have consistent stroke production and can hit medium-paced shots with some direction.",
                    "zh-Hant": "這是參加聯賽最常見的起步水平。你的擊球已經穩定，能打出有一定方向的中等速度球。",
                    "zh-Hans": "这是参加联赛最常见的起步水平。你的击球已经稳定，能打出有一定方向的中等速度球。",
                },
            },
        ],
        "skills": [
            {
                "name": {
                    "en": "Net Play",
                    "zh-Hant": "網前",
                    "zh-Hans": "网前",
                },
                "description": {
                    "en": "Comfortable at the net and can hit basic volleys.",
                    "zh-Hant": "在網前感到自在，能打出基本的截擊。",
                    "zh-Hans": "在网前感到自在，能打出基本的截击。",
                },
            },
            {
                "name": {
                    "en": "Strategy",
                    "zh-Hant": "策略",
                    "zh-Hans": "策略",
                },
                "description": {
                    "en": "Understands basic doubles positioning (one up, one back).",
                    "zh-Hant": "了解基本的雙打站位（一前一後）。",
                    "zh-Hans": "了解基本的双打站位（一前一后）。",
                },
            },
        ],
    },
    {
        "title": {
            "en": "Level 3.5 – 4.0: The Competitive Intermediate",
            "zh-Hant": "等級 3.5 – 4.0：競技中級",
            "zh-Hans": "等级 3.5 – 4.0：竞技中级",
        },
        "levels": [
            {
                "level": "3.5",
                "description": {
                    "en": "You have achieved improved stroke dependability and direction on moderate shots. You are starting to use lobs, overheads, and approach shots with success.",
                    "zh-Hant": "你的擊球穩定性和方向控制有所提升。你開始能成功運用高吊球、高壓球和上網進攻。",
                    "zh-Hans": "你的击球稳定性和方向控制有所提升。你开始能成功运用高吊球、高压球和上网进攻。",
                },
            },
            {
                "level": "4.0",
                "description": {
                    "en": "You have dependable strokes, including directional control and depth on both forehand and backhand sides.",
                    "zh-Hant": "你的正反手擊球穩定可靠，能控制方向和深度。",
                    "zh-Hans": "你的正反手击球稳定可靠，能控制方向和深度。",
                },
            },
        ],
        "skills": [
            {
                "name": {
                    "en": "Serve",
                    "zh-Hant": "發球",
                    "zh-Hans": "发球",
                },
                "description": {
                    "en": "You can use power and spin and are beginning to hit a \"forcing\" second serve.",
                    "zh-Hant": "你能運用力量和旋轉，並開始打出有威脅性的二發。",
                    "zh-Hans": "你能运用力量和旋转，并开始打出有威胁性的二发。",
                },
            },
            {
                "name": {
                    "en": "Rally",
                    "zh-Hant": "對打",
                    "zh-Hans": "对打",
                },
                "description": {
                    "en": "You can consistently rally from the baseline and \"construct\" points rather than just reacting.",
                    "zh-Hant": "你能穩定地從底線對打，並主動「組織」得分，而非單純回應。",
                    "zh-Hans": "你能稳定地从底线对打，并主动「组织」得分，而非单纯回应。",
                },
            },
        ],
    },
    {
        "title": {
            "en": "Level 4.5 – 5.0: The Advanced Player",
            "zh-Hant": "等級 4.5 – 5.0：高級選手",
            "zh-Hans": "等级 4.5 – 5.0：高级选手",
        },
        "levels": [
            {
                "level": "4.5",
                "description": {
                    "en": "You have begun to master the use of power and spin. You can handle pace, have sound footwork, and can control depth of shots.",
                    "zh-Hant": "你開始掌握力量和旋轉的運用。你能應對快節奏、步伐扎實，並能控制擊球深度。",
                    "zh-Hans": "你开始掌握力量和旋转的运用。你能应对快节奏、步伐扎实，并能控制击球深度。",
                },
            },
            {
                "level": "5.0",
                "description": {
                    "en": "You have good shot anticipation and frequently have an outstanding shot or weapon around which a game may be structured.",
                    "zh-Hant": "你有良好的預判能力，且通常擁有一項突出的技術或武器，可以圍繞它構建比賽策略。",
                    "zh-Hans": "你有良好的预判能力，且通常拥有一项突出的技术或武器，可以围绕它构建比赛策略。",
                },
            },
        ],
        "skills": [
            {
                "name": {
                    "en": "Strategy",
                    "zh-Hant": "策略",
                    "zh-Hans": "策略",
                },
                "description": {
                    "en": "You can vary game plans according to opponents. You hit winners or force errors off of short balls.",
                    "zh-Hant": "你能根據對手調整比賽計畫。你能在短球上打出致勝球或迫使對手失誤。",
                    "zh-Hans": "你能根据对手调整比赛计划。你能在短球上打出致胜球或迫使对手失误。",
                },
            },
        ],
    },
    {
        "title": {
            "en": "Level 5.5 – 7.0: The Elite / Professional",
            "zh-Hant": "等級 5.5 – 7.0：精英 / 職業",
            "zh-Hans": "等级 5.5 – 7.0：精英 / 职业",
        },
        "levels": [
            {
                "level": "5.5",
                "description": {
                    "en": "You have developed a high-level of consistency and can hit \"heavy\" balls with power and variety.",
                    "zh-Hant": "你已具備高度穩定性，能打出帶有力量和變化的「重球」。",
                    "zh-Hans": "你已具备高度稳定性，能打出带有力量和变化的「重球」。",
                },
            },
            {
                "level": "6.0",
                "description": {
                    "en": "These ratings are typically reserved for players who have had intensive training for national tournament competition or are professional tour players.",
                    "zh-Hant": "此等級通常保留給經過密集訓練、參加全國性錦標賽或職業巡迴賽的選手。",
                    "zh-Hans": "此等级通常保留给经过密集训练、参加全国性锦标赛或职业巡回赛的选手。",
                },
            },
        ],
        "skills": [],
    },
]


def _resolve_lang(text: dict[str, str], lang: str) -> str:
    """Pick the requested language, falling back to zh-Hant then en."""
    return text.get(lang) or text.get("zh-Hant") or text.get("en", "")


def get_level_guide(lang: str) -> list[dict]:
    """Return NTRP level groups with text resolved to the given language."""
    groups = []
    for g in LEVEL_GROUPS:
        groups.append(
            {
                "title": _resolve_lang(g["title"], lang),
                "levels": [
                    {
                        "level": lv["level"],
                        "description": _resolve_lang(lv["description"], lang),
                    }
                    for lv in g["levels"]
                ],
                "skills": [
                    {
                        "name": _resolve_lang(sk["name"], lang),
                        "description": _resolve_lang(sk["description"], lang),
                    }
                    for sk in g["skills"]
                ],
            }
        )
    return groups
```

- [ ] **Step 2: Commit**

```bash
git add app/services/ntrp_guide.py
git commit -m "feat(ntrp): add trilingual level guide service"
```

---

### Task 3: Router + Registration

**Files:**

- Create: `app/routers/ntrp_guide.py`
- Modify: `app/main.py:27,30-46`

- [ ] **Step 1: Create router**

Create `app/routers/ntrp_guide.py`:

```python
from fastapi import APIRouter

from app.dependencies import Lang
from app.schemas.ntrp_guide import LevelGuideResponse
from app.services.ntrp_guide import get_level_guide

router = APIRouter()


@router.get("/levels", response_model=LevelGuideResponse)
async def get_levels(lang: Lang):
    groups = get_level_guide(lang)
    return LevelGuideResponse(groups=groups)
```

- [ ] **Step 2: Register router in main.py**

In `app/main.py`, add the import and registration.

Add to the import line (line 27):

```python
from app.routers import auth, assistant, blocks, booking_invite, bookings, chat, courts, devices, events, follows, matching, notifications, ntrp_guide, reports, reviews, users, weather
```

Add after the weather router registration (after line 44):

```python
    app.include_router(ntrp_guide.router, prefix="/api/v1/ntrp", tags=["ntrp"])
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_ntrp_guide.py -v`
Expected: 2 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/routers/ntrp_guide.py app/main.py
git commit -m "feat(ntrp): add GET /api/v1/ntrp/levels endpoint"
```

---

### Task 4: Language Tests

**Files:**

- Modify: `tests/test_ntrp_guide.py`

- [ ] **Step 1: Add language-specific tests**

Append to `tests/test_ntrp_guide.py`:

```python
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
    import re
    for group in resp.json()["groups"]:
        for level in group["levels"]:
            assert re.match(r"^\d\.\d$", level["level"]), f"Bad level: {level['level']}"


@pytest.mark.asyncio
async def test_ntrp_levels_no_auth_required(client: AsyncClient):
    """Endpoint works without any Authorization header."""
    resp = await client.get("/api/v1/ntrp/levels")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/test_ntrp_guide.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ntrp_guide.py
git commit -m "test(ntrp): add language and validation tests for level guide"
```

---

### Task 5: Full Test Suite Verification

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS. No regressions.

- [ ] **Step 2: Final commit (if any fixups needed)**

If any test needed fixing, commit the fix. Otherwise, this task is done.
