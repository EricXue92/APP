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
