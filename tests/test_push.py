import json
import uuid

import pytest

from unittest.mock import AsyncMock, MagicMock

from app.i18n import t
from app.models.notification import Notification, NotificationType
from app.services.push import PUSHABLE_TYPES, enqueue_push


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


def _make_notification(
    type: NotificationType,
    recipient_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
) -> Notification:
    n = Notification(
        id=uuid.uuid4(),
        recipient_id=recipient_id or uuid.uuid4(),
        actor_id=actor_id,
        type=type,
        target_type=target_type,
        target_id=target_id,
    )
    return n


@pytest.mark.asyncio
async def test_enqueue_push_pushable_type():
    redis = AsyncMock()
    notification = _make_notification(NotificationType.BOOKING_CONFIRMED, target_type="booking", target_id=uuid.uuid4())
    result = await enqueue_push(redis, notification)
    assert result is True
    redis.lpush.assert_called_once()
    payload = json.loads(redis.lpush.call_args[0][1])
    assert payload["type"] == "booking_confirmed"


@pytest.mark.asyncio
async def test_enqueue_push_non_pushable_type():
    redis = AsyncMock()
    notification = _make_notification(NotificationType.NEW_FOLLOWER)
    result = await enqueue_push(redis, notification)
    assert result is False
    redis.lpush.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_push_chat_skips_when_online():
    redis = AsyncMock()
    recipient_id = uuid.uuid4()
    notification = _make_notification(NotificationType.NEW_CHAT_MESSAGE, recipient_id=recipient_id)

    ws_manager = MagicMock()
    ws_manager.connections = {recipient_id: MagicMock()}

    result = await enqueue_push(redis, notification, ws_manager=ws_manager)
    assert result is False
    redis.lpush.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_push_chat_sends_when_offline():
    redis = AsyncMock()
    recipient_id = uuid.uuid4()
    notification = _make_notification(NotificationType.NEW_CHAT_MESSAGE, recipient_id=recipient_id)

    ws_manager = MagicMock()
    ws_manager.connections = {}

    result = await enqueue_push(redis, notification, ws_manager=ws_manager)
    assert result is True
    redis.lpush.assert_called_once()


@pytest.mark.asyncio
async def test_enqueue_push_chat_sends_when_no_manager():
    redis = AsyncMock()
    notification = _make_notification(NotificationType.NEW_CHAT_MESSAGE)
    result = await enqueue_push(redis, notification, ws_manager=None)
    assert result is True
    redis.lpush.assert_called_once()


@pytest.mark.asyncio
async def test_pushable_types_count():
    assert len(PUSHABLE_TYPES) == 8


from app.services.push import build_push_message, send_fcm


@pytest.mark.asyncio
async def test_build_push_message_en():
    title, body = build_push_message("booking_confirmed", "en")
    assert title == "Booking Confirmed"
    assert "confirmed" in body.lower()


@pytest.mark.asyncio
async def test_build_push_message_zh_hant():
    title, body = build_push_message("booking_confirmed", "zh-Hant")
    assert "確認" in title


@pytest.mark.asyncio
async def test_build_push_message_all_types():
    for ntype in PUSH_TYPES:
        title, body = build_push_message(ntype, "en")
        assert len(title) > 0
        assert len(body) > 0


@pytest.mark.asyncio
async def test_send_fcm_returns_stale_tokens(monkeypatch):
    from unittest.mock import patch, MagicMock
    import firebase_admin.messaging as fcm_module

    mock_response = MagicMock()
    mock_response.responses = [
        MagicMock(success=True, exception=None),
        MagicMock(success=False, exception=MagicMock(code="UNREGISTERED")),
        MagicMock(success=False, exception=MagicMock(code="INTERNAL")),
    ]

    with patch.object(fcm_module, "send_each_for_multicast", return_value=mock_response):
        stale = await send_fcm(
            tokens=["good-token", "stale-token", "error-token"],
            title="Test",
            body="Test body",
            data={"type": "booking_confirmed"},
        )

    assert stale == ["stale-token"]


@pytest.mark.asyncio
async def test_send_fcm_empty_tokens():
    stale = await send_fcm(tokens=[], title="Test", body="Body", data={})
    assert stale == []
