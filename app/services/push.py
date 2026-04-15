from __future__ import annotations

import json
import logging
import uuid

import firebase_admin
from firebase_admin import credentials, messaging
from redis.asyncio import Redis

from app.config import settings
from app.i18n import t
from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)

PUSHABLE_TYPES: set[NotificationType] = {
    NotificationType.BOOKING_CONFIRMED,
    NotificationType.BOOKING_CANCELLED,
    NotificationType.MATCH_PROPOSAL_RECEIVED,
    NotificationType.EVENT_MATCH_READY,
    NotificationType.EVENT_SCORE_SUBMITTED,
    NotificationType.EVENT_SCORE_DISPUTED,
    NotificationType.ACCOUNT_SUSPENDED,
    NotificationType.NEW_CHAT_MESSAGE,
}

PUSH_QUEUE_KEY = "push:queue"


async def enqueue_push(
    redis: Redis,
    notification: Notification,
    *,
    ws_manager=None,
) -> bool:
    if notification.type not in PUSHABLE_TYPES:
        return False

    if notification.type == NotificationType.NEW_CHAT_MESSAGE and ws_manager is not None:
        if notification.recipient_id in ws_manager.connections:
            return False

    payload = json.dumps({
        "notification_id": str(notification.id),
        "recipient_id": str(notification.recipient_id),
        "type": notification.type.value,
        "actor_id": str(notification.actor_id) if notification.actor_id else None,
        "target_type": notification.target_type,
        "target_id": str(notification.target_id) if notification.target_id else None,
    })

    await redis.lpush(PUSH_QUEUE_KEY, payload)
    return True


def _init_firebase() -> bool:
    if firebase_admin._apps:
        return True
    if not settings.firebase_credentials_path:
        logger.warning("firebase_credentials_path not set, push disabled")
        return False
    cred = credentials.Certificate(settings.firebase_credentials_path)
    firebase_admin.initialize_app(cred)
    return True


def build_push_message(notification_type: str, lang: str) -> tuple[str, str]:
    title = t(f"push.{notification_type}.title", lang)
    body = t(f"push.{notification_type}.body", lang)
    return title, body


async def send_fcm(
    *,
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str],
) -> list[str]:
    if not tokens:
        return []

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data,
        tokens=tokens,
    )

    response = messaging.send_each_for_multicast(message)

    stale_tokens: list[str] = []
    for i, send_response in enumerate(response.responses):
        if not send_response.success and send_response.exception:
            if getattr(send_response.exception, "code", "") == "UNREGISTERED":
                stale_tokens.append(tokens[i])
            else:
                logger.error(
                    "FCM send failed for token %s: %s",
                    tokens[i],
                    send_response.exception,
                )

    return stale_tokens
