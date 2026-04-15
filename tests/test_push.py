import pytest

from app.i18n import t


PUSH_TYPES = [
    "booking_confirmed",
    "booking_cancelled",
    "match_proposal_received",
    "event_match_ready",
    "event_score_submitted",
    "event_score_disputed",
    "account_suspended",
    "new_chat_message",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("ntype", PUSH_TYPES)
async def test_push_i18n_title_exists(ntype: str):
    for lang in ("zh-Hant", "zh-Hans", "en"):
        key = f"push.{ntype}.title"
        result = t(key, lang)
        assert result != key, f"Missing i18n key: {key} for lang={lang}"


@pytest.mark.asyncio
@pytest.mark.parametrize("ntype", PUSH_TYPES)
async def test_push_i18n_body_exists(ntype: str):
    for lang in ("zh-Hant", "zh-Hans", "en"):
        key = f"push.{ntype}.body"
        result = t(key, lang)
        assert result != key, f"Missing i18n key: {key} for lang={lang}"
