from __future__ import annotations

import json
import logging
import uuid

from redis.asyncio import Redis

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
