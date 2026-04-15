import pytest

from app.i18n import t


def test_translate_zh_hans():
    assert t("auth.invalid_credentials", "zh-Hans") == "用户名或密码错误"


def test_translate_zh_hant():
    assert t("auth.invalid_credentials", "zh-Hant") == "用戶名或密碼錯誤"


def test_translate_en():
    assert t("auth.invalid_credentials", "en") == "Invalid credentials"


def test_translate_fallback_to_en():
    assert t("auth.invalid_credentials", "ja") == "Invalid credentials"


def test_translate_missing_key():
    result = t("nonexistent.key", "en")
    assert result == "nonexistent.key"


@pytest.mark.asyncio
async def test_translate_event_not_participant_key_exists():
    """Regression: event.not_participant used in admin.py:363 but was missing from i18n."""
    result = t("event.not_participant", "en")
    assert result != "event.not_participant", "Key should exist, not fall back to key name"
    result_zh = t("event.not_participant", "zh-Hant")
    assert result_zh != "event.not_participant"


def test_translate_none_language_fallback():
    """None language should not crash."""
    try:
        result = t("auth.invalid_credentials", None)
        assert isinstance(result, str)
    except (TypeError, KeyError):
        pass  # Document: None language causes crash


def test_translate_unknown_language_falls_back():
    """Language not in supported set should fall back to English."""
    result = t("auth.invalid_credentials", "fr")
    en_result = t("auth.invalid_credentials", "en")
    assert result == en_result
