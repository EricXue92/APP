# Booking Assistant Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an AI-powered natural language booking parser that turns free text into pre-filled booking form fields via Claude API.

**Architecture:** Protocol-based LLM adapter (`LLMProvider` interface + `ClaudeProvider` implementation + provider registry) → Assistant service (rate limiting, prompt building, court fuzzy matching) → REST endpoint. FakeProvider in tests, no real LLM calls.

**Tech Stack:** `anthropic` Python SDK, Redis (rate limiting), existing SQLAlchemy/FastAPI patterns.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `app/services/llm.py` | **New** — `LLMProvider` protocol, `RateLimitError`, `ClaudeProvider`, provider registry, `get_provider()` |
| `app/services/assistant.py` | **New** — `parse_booking()`: rate limit check, prompt building, LLM call, court fuzzy match |
| `app/schemas/assistant.py` | **New** — `ParseBookingRequest`, `ParseBookingResponse` |
| `app/routers/assistant.py` | **New** — `POST /api/v1/assistant/parse-booking` |
| `app/config.py` | **Modify** — Add LLM config fields |
| `app/main.py` | **Modify** — Register assistant router |
| `app/i18n.py` | **Modify** — Add assistant error messages |
| `tests/test_assistant.py` | **New** — 9 test cases with FakeProvider |
| `pyproject.toml` | **Modify** — Add `anthropic` dependency |

---

### Task 1: Add `anthropic` dependency and config fields

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/config.py`

- [ ] **Step 1: Add anthropic dependency**

```bash
uv add anthropic
```

- [ ] **Step 2: Add LLM config fields to `app/config.py`**

Add these fields to the `Settings` class, after the existing `supported_languages` field:

```python
    # LLM / Booking Assistant
    llm_provider: str = "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    assistant_rate_limit: int = 10  # per user per hour
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock app/config.py
git commit -m "feat: add anthropic dependency and LLM config fields"
```

---

### Task 2: LLM adapter layer — protocol, RateLimitError, ClaudeProvider, registry

**Files:**
- Create: `app/services/llm.py`
- Test: `tests/test_assistant.py` (partial — LLM unit tests)

- [ ] **Step 1: Write failing tests for the LLM layer**

Create `tests/test_assistant.py`:

```python
import pytest

from app.services.llm import RateLimitError, get_provider


@pytest.mark.asyncio
async def test_get_provider_returns_claude_by_default():
    provider = get_provider()
    assert provider is not None
    assert hasattr(provider, "parse")


@pytest.mark.asyncio
async def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("nonexistent")


def test_rate_limit_error_is_exception():
    err = RateLimitError("too many requests")
    assert isinstance(err, Exception)
    assert str(err) == "too many requests"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_assistant.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.llm'`

- [ ] **Step 3: Implement `app/services/llm.py`**

```python
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import anthropic

from app.config import settings


class RateLimitError(Exception):
    """Raised when a user exceeds the assistant rate limit."""


@runtime_checkable
class LLMProvider(Protocol):
    async def parse(self, system: str, user_message: str) -> dict[str, Any]: ...


class ClaudeProvider:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def parse(self, system: str, user_message: str) -> dict[str, Any]:
        tool = {
            "name": "extract_booking",
            "description": "Extract structured booking fields from user text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "match_type": {"type": ["string", "null"], "enum": ["singles", "doubles", None]},
                    "play_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "start_time": {"type": ["string", "null"], "description": "HH:MM"},
                    "end_time": {"type": ["string", "null"], "description": "HH:MM"},
                    "court_keyword": {"type": ["string", "null"]},
                    "min_ntrp": {"type": ["string", "null"]},
                    "max_ntrp": {"type": ["string", "null"]},
                    "gender_requirement": {"type": ["string", "null"], "enum": ["male_only", "female_only", "any", None]},
                    "cost_description": {"type": ["string", "null"]},
                },
                "required": [
                    "match_type", "play_date", "start_time", "end_time",
                    "court_keyword", "min_ntrp", "max_ntrp",
                    "gender_requirement", "cost_description",
                ],
            },
        }

        response = await self._client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[tool],
            tool_choice={"type": "tool", "name": "extract_booking"},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_booking":
                return block.input

        return {
            "match_type": None, "play_date": None, "start_time": None,
            "end_time": None, "court_keyword": None, "min_ntrp": None,
            "max_ntrp": None, "gender_requirement": None, "cost_description": None,
        }


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    provider_name = name or settings.llm_provider
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
    return cls()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_assistant.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/services/llm.py tests/test_assistant.py
git commit -m "feat: add LLM adapter layer with ClaudeProvider and registry"
```

---

### Task 3: Schemas

**Files:**
- Create: `app/schemas/assistant.py`

- [ ] **Step 1: Create `app/schemas/assistant.py`**

```python
from pydantic import BaseModel, Field


class ParseBookingRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=500)


class ParseBookingResponse(BaseModel):
    match_type: str | None = None
    play_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    court_keyword: str | None = None
    court_id: str | None = None
    court_name: str | None = None
    min_ntrp: str | None = None
    max_ntrp: str | None = None
    gender_requirement: str | None = None
    cost_description: str | None = None
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/assistant.py
git commit -m "feat: add assistant request/response schemas"
```

---

### Task 4: Assistant service — rate limit, prompt, LLM call, court match

**Files:**
- Create: `app/services/assistant.py`
- Modify: `app/i18n.py`
- Test: `tests/test_assistant.py` (extend)

- [ ] **Step 1: Add i18n messages for assistant errors**

Add to the `_MESSAGES` dict in `app/i18n.py`:

```python
    "assistant.rate_limit": {
        "zh-Hans": "请求过于频繁，请稍后再试",
        "zh-Hant": "請求過於頻繁，請稍後再試",
        "en": "Too many requests, please try again later",
    },
    "assistant.llm_error": {
        "zh-Hans": "AI 服务暂时不可用",
        "zh-Hant": "AI 服務暫時不可用",
        "en": "AI service temporarily unavailable",
    },
```

- [ ] **Step 2: Write failing tests for the assistant service**

Append to `tests/test_assistant.py`:

```python
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.user import AuthProvider
from app.services.assistant import parse_booking
from app.services.llm import RateLimitError
from app.services.user import create_user_with_auth


class FakeProvider:
    """Test double that returns canned LLM responses."""

    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response = response or {
            "match_type": "singles",
            "play_date": "2026-04-19",
            "start_time": "15:00",
            "end_time": "17:00",
            "court_keyword": "维园",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
            "cost_description": "AA",
        }
        self.error = error
        self.last_system: str | None = None
        self.last_user_message: str | None = None

    async def parse(self, system: str, user_message: str) -> dict[str, Any]:
        self.last_system = system
        self.last_user_message = user_message
        if self.error:
            raise self.error
        return self.response


async def _create_test_user(session: AsyncSession, username: str = "testuser") -> "User":
    return await create_user_with_auth(
        session,
        nickname=f"Player_{username}",
        gender="male",
        city="Hong Kong",
        ntrp_level="3.5",
        language="en",
        provider=AuthProvider.USERNAME,
        provider_user_id=username,
        password="test1234",
    )


async def _seed_test_court(session: AsyncSession, name: str = "Victoria Park Tennis") -> Court:
    court = Court(
        name=name,
        address="Victoria Park, Causeway Bay",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


@pytest.mark.asyncio
async def test_parse_booking_happy_path(session: AsyncSession):
    user = await _create_test_user(session, "happy_user")
    court = await _seed_test_court(session, "维园网球场")
    fake = FakeProvider()

    with patch("app.services.assistant.get_provider", return_value=fake):
        with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock):
            result = await parse_booking(session, user, "这周六下午维园单打 3.5 AA", "zh-Hant")

    assert result["match_type"] == "singles"
    assert result["play_date"] == "2026-04-19"
    assert result["court_id"] == str(court.id)
    assert result["court_name"] == "维园网球场"
    assert result["cost_description"] == "AA"


@pytest.mark.asyncio
async def test_parse_booking_partial_input(session: AsyncSession):
    user = await _create_test_user(session, "partial_user")
    partial_response = {
        "match_type": "doubles",
        "play_date": None, "start_time": None, "end_time": None,
        "court_keyword": None, "min_ntrp": None, "max_ntrp": None,
        "gender_requirement": None, "cost_description": None,
    }
    fake = FakeProvider(response=partial_response)

    with patch("app.services.assistant.get_provider", return_value=fake):
        with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock):
            result = await parse_booking(session, user, "want to play doubles", "en")

    assert result["match_type"] == "doubles"
    assert result["play_date"] is None
    assert result["court_id"] is None


@pytest.mark.asyncio
async def test_parse_booking_court_no_match(session: AsyncSession):
    user = await _create_test_user(session, "nomatch_user")
    fake = FakeProvider(response={
        "match_type": "singles",
        "play_date": None, "start_time": None, "end_time": None,
        "court_keyword": "不存在的球场",
        "min_ntrp": None, "max_ntrp": None,
        "gender_requirement": None, "cost_description": None,
    })

    with patch("app.services.assistant.get_provider", return_value=fake):
        with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock):
            result = await parse_booking(session, user, "在不存在的球场打球", "zh-Hant")

    assert result["court_keyword"] == "不存在的球场"
    assert result["court_id"] is None
    assert result["court_name"] is None


@pytest.mark.asyncio
async def test_parse_booking_user_context_in_prompt(session: AsyncSession):
    user = await _create_test_user(session, "context_user")
    fake = FakeProvider()

    with patch("app.services.assistant.get_provider", return_value=fake):
        with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock):
            await parse_booking(session, user, "play singles", "en")

    # User's city should appear in the system prompt
    assert "Hong Kong" in fake.last_system


@pytest.mark.asyncio
async def test_parse_booking_rate_limit(session: AsyncSession):
    user = await _create_test_user(session, "ratelimit_user")

    with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock, side_effect=RateLimitError("rate limit")):
        with pytest.raises(RateLimitError):
            await parse_booking(session, user, "play singles", "en")


@pytest.mark.asyncio
async def test_parse_booking_llm_failure(session: AsyncSession):
    user = await _create_test_user(session, "llmfail_user")
    fake = FakeProvider(error=RuntimeError("API down"))

    with patch("app.services.assistant.get_provider", return_value=fake):
        with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="API down"):
                await parse_booking(session, user, "play singles", "en")


@pytest.mark.asyncio
async def test_parse_booking_malformed_response(session: AsyncSession):
    user = await _create_test_user(session, "malformed_user")
    fake = FakeProvider(response={"garbage": True})

    with patch("app.services.assistant.get_provider", return_value=fake):
        with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock):
            result = await parse_booking(session, user, "play singles", "en")

    # All standard fields should be None when LLM returns garbage
    assert result["match_type"] is None
    assert result["court_id"] is None
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_assistant.py::test_parse_booking_happy_path -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.assistant'`

- [ ] **Step 4: Implement `app/services/assistant.py`**

```python
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.redis import redis_client
from app.services.court import search_courts_by_keyword
from app.services.llm import RateLimitError, get_provider

_EXPECTED_FIELDS = [
    "match_type", "play_date", "start_time", "end_time",
    "court_keyword", "min_ntrp", "max_ntrp",
    "gender_requirement", "cost_description",
]


async def _check_rate_limit(user_id: str) -> None:
    key = f"assistant:{user_id}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 3600)
    if count > settings.assistant_rate_limit:
        raise RateLimitError("rate limit exceeded")


def _build_system_prompt(user: User, lang: str) -> str:
    today = date.today().isoformat()

    if lang.startswith("zh"):
        return (
            "你是一个网球约球助手。从用户的自然语言输入中提取约球信息。\n"
            f"今天日期：{today}\n"
            f"用户所在城市：{user.city}\n"
            "请使用 extract_booking 工具返回结构化数据。"
            "未提及的字段设为 null。"
        )
    return (
        "You are a tennis booking assistant. Extract booking details from the user's natural language input.\n"
        f"Today's date: {today}\n"
        f"User's city: {user.city}\n"
        "Use the extract_booking tool to return structured data. "
        "Set unmentioned fields to null."
    )


def _normalize_response(raw: dict[str, Any]) -> dict[str, Any]:
    return {field: raw.get(field) for field in _EXPECTED_FIELDS}


async def parse_booking(
    session: AsyncSession,
    user: User,
    text: str,
    lang: str,
) -> dict[str, Any]:
    await _check_rate_limit(str(user.id))

    system = _build_system_prompt(user, lang)
    provider = get_provider()

    raw = await provider.parse(system, text)
    result = _normalize_response(raw)

    # Court fuzzy match
    court_keyword = result.get("court_keyword")
    result["court_id"] = None
    result["court_name"] = None
    if court_keyword:
        courts = await search_courts_by_keyword(session, court_keyword)
        if courts:
            result["court_id"] = str(courts[0].id)
            result["court_name"] = courts[0].name

    return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_assistant.py -v
```

Expected: 10 PASSED (3 from Task 2 + 7 new)

- [ ] **Step 6: Commit**

```bash
git add app/services/assistant.py app/i18n.py tests/test_assistant.py
git commit -m "feat: add assistant service with rate limiting and court matching"
```

---

### Task 5: Router and app registration

**Files:**
- Create: `app/routers/assistant.py`
- Modify: `app/main.py`
- Test: `tests/test_assistant.py` (extend)

- [ ] **Step 1: Write failing HTTP-level tests**

Append to `tests/test_assistant.py`:

```python
async def _register_and_get_token(client: AsyncClient, username: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


@pytest.mark.asyncio
async def test_api_parse_booking_success(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "api_user")
    court = await _seed_test_court(session, "维园网球场API")

    fake = FakeProvider(response={
        "match_type": "singles",
        "play_date": "2026-04-19",
        "start_time": "15:00",
        "end_time": "17:00",
        "court_keyword": "维园",
        "min_ntrp": "3.0",
        "max_ntrp": "4.0",
        "gender_requirement": "any",
        "cost_description": "AA",
    })

    with patch("app.services.assistant.get_provider", return_value=fake):
        with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock):
            resp = await client.post(
                "/api/v1/assistant/parse-booking",
                headers={"Authorization": f"Bearer {token}"},
                json={"text": "周六下午维园单打 3.5 AA"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["match_type"] == "singles"
    assert data["court_name"] == "维园网球场API"


@pytest.mark.asyncio
async def test_api_parse_booking_no_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/assistant/parse-booking",
        json={"text": "play singles"},
    )
    assert resp.status_code == 422  # missing Authorization header


@pytest.mark.asyncio
async def test_api_parse_booking_rate_limited(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "rate_api_user")

    with patch("app.services.assistant.parse_booking", new_callable=AsyncMock, side_effect=RateLimitError("rate limit")):
        resp = await client.post(
            "/api/v1/assistant/parse-booking",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "play singles"},
        )

    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_api_parse_booking_llm_error(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "err_api_user")

    with patch("app.services.assistant.parse_booking", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
        resp = await client.post(
            "/api/v1/assistant/parse-booking",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "play singles"},
        )

    assert resp.status_code == 502
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_assistant.py::test_api_parse_booking_success -v
```

Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Create `app/routers/assistant.py`**

```python
from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.assistant import ParseBookingRequest, ParseBookingResponse
from app.services.assistant import parse_booking
from app.services.llm import RateLimitError

router = APIRouter()


@router.post("/parse-booking", response_model=ParseBookingResponse)
async def parse_booking_endpoint(
    body: ParseBookingRequest,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
):
    try:
        result = await parse_booking(session, user, body.text, lang)
    except RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=t("assistant.rate_limit", lang),
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=t("assistant.llm_error", lang),
        )

    return ParseBookingResponse(**result)
```

- [ ] **Step 4: Register router in `app/main.py`**

Add to the import line inside `create_app()`:

```python
from app.routers import auth, assistant, blocks, bookings, courts, follows, notifications, reports, reviews, users
```

Add after the existing `include_router` calls:

```python
app.include_router(assistant.router, prefix="/api/v1/assistant", tags=["assistant"])
```

- [ ] **Step 5: Run all assistant tests**

```bash
uv run pytest tests/test_assistant.py -v
```

Expected: 14 PASSED

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/routers/assistant.py app/main.py tests/test_assistant.py
git commit -m "feat: add assistant router with parse-booking endpoint"
```

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

The `Booking assistant` entry already exists in CLAUDE.md under **Key patterns**. Verify it is accurate and matches the implementation. If not, update it. The entry should read:

> **Booking assistant (约球助理)**: `services/llm.py` + `services/assistant.py` + `routers/assistant.py` — AI-powered natural language booking form filler. User inputs free text, backend calls LLM (Claude, configurable via `LLM_PROVIDER`) to parse into structured booking fields, then fuzzy-matches court keywords against Court table. Returns pre-filled form data; final submission still goes through `create_booking`. Rate-limited per user via Redis (`ASSISTANT_RATE_LIMIT`).

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with booking assistant implementation details"
```
