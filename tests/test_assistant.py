from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType
from app.models.user import AuthProvider
from app.services.assistant import _build_system_prompt, _normalize_response, parse_booking
from app.services.llm import ClaudeProvider, RateLimitError, get_provider
from app.services.user import create_user_with_auth


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


# ── Gap tests ──────────────────────────────────────────────────────────────────


def test_normalize_response_strips_extra_fields():
    """Extra keys in the LLM response are dropped; expected fields are preserved."""
    raw = {
        "match_type": "singles",
        "play_date": "2026-04-19",
        "start_time": "10:00",
        "end_time": "12:00",
        "court_keyword": "维园",
        "min_ntrp": "3.0",
        "max_ntrp": "4.5",
        "gender_requirement": "any",
        "cost_description": "AA",
        # extra keys that should be stripped
        "unexpected_field": "should_be_removed",
        "another_extra": 42,
    }
    result = _normalize_response(raw)

    # Only the nine expected fields should be present
    expected_keys = {
        "match_type", "play_date", "start_time", "end_time",
        "court_keyword", "min_ntrp", "max_ntrp",
        "gender_requirement", "cost_description",
    }
    assert set(result.keys()) == expected_keys
    assert "unexpected_field" not in result
    assert "another_extra" not in result
    assert result["match_type"] == "singles"
    assert result["court_keyword"] == "维园"


def test_build_system_prompt_zh_hans():
    """zh-Hans prompt contains simplified Chinese characters."""
    user = MagicMock()
    user.city = "上海"

    prompt = _build_system_prompt(user, "zh-Hans")

    # Simplified Chinese indicator: 约球助手 (not 約球助手)
    assert "约球助手" in prompt
    assert "上海" in prompt
    # Should NOT contain traditional Chinese indicator
    assert "約球助手" not in prompt


@pytest.mark.asyncio
async def test_claude_provider_parse_no_tool_use_returns_null_dict():
    """When the API response contains no tool_use block, parse() returns all-null dict."""
    provider = ClaudeProvider.__new__(ClaudeProvider)

    # Build a mock response whose content has no tool_use blocks
    mock_text_block = MagicMock()
    mock_text_block.type = "text"

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    provider._client = mock_client

    result = await provider.parse("system prompt", "user message")

    assert result["match_type"] is None
    assert result["play_date"] is None
    assert result["court_keyword"] is None
    assert set(result.keys()) == {
        "match_type", "play_date", "start_time", "end_time",
        "court_keyword", "min_ntrp", "max_ntrp",
        "gender_requirement", "cost_description",
    }


@pytest.mark.asyncio
async def test_parse_booking_empty_court_keyword_no_crash(session: AsyncSession):
    """Empty string court_keyword is treated as absent — no court search attempted."""
    user = await _create_test_user(session, "empty_kw_user")
    fake = FakeProvider(response={
        "match_type": "singles",
        "play_date": None,
        "start_time": None,
        "end_time": None,
        "court_keyword": "",   # empty string
        "min_ntrp": None,
        "max_ntrp": None,
        "gender_requirement": None,
        "cost_description": None,
    })

    with patch("app.services.assistant.get_provider", return_value=fake):
        with patch("app.services.assistant._check_rate_limit", new_callable=AsyncMock):
            result = await parse_booking(session, user, "play singles", "en")

    # Should return without error; court_id and court_name remain None
    assert result["match_type"] == "singles"
    assert result["court_id"] is None
    assert result["court_name"] is None
