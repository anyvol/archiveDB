"""Browser Web Push helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from pywebpush import WebPushException, webpush
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import VAPID_CLAIMS, VAPID_PRIVATE_KEY
from app.models import NotificationEventType, User

logger = logging.getLogger(__name__)

PUSH_EVENT_KEYS = {
    NotificationEventType.upload: "upload",
    NotificationEventType.status_change: "status_change",
    NotificationEventType.document_edit: "document_edit",
    NotificationEventType.document_register: "document_register",
    NotificationEventType.document_delete: "document_delete",
    NotificationEventType.correction_request: "correction_request",
    NotificationEventType.correction_request_response: "correction_request_response",
    NotificationEventType.formal_change: "formal_change",
}

DEFAULT_PUSH_PREFERENCES: dict[str, bool] = {
    "enabled": False,
    "upload": True,
    "status_change": True,
    "document_edit": True,
    "document_register": True,
    "document_delete": True,
    "correction_request": True,
    "correction_request_response": True,
    "formal_change": True,
}


def normalize_push_preferences(raw: dict[str, Any] | None) -> dict[str, bool]:
    prefs = dict(DEFAULT_PUSH_PREFERENCES)
    if not raw:
        return prefs
    for key in DEFAULT_PUSH_PREFERENCES:
        if key in raw:
            prefs[key] = bool(raw[key])
    return prefs


def user_wants_push(user: User, event_type: NotificationEventType) -> bool:
    prefs = normalize_push_preferences(user.push_preferences)
    if not prefs.get("enabled"):
        return False
    event_key = PUSH_EVENT_KEYS.get(event_type)
    if not event_key:
        return False
    return prefs.get(event_key, True)


def send_web_push(
    subscription: dict[str, Any],
    message: str,
    *,
    document_id: int | None = None,
) -> bool:
    if not VAPID_PRIVATE_KEY:
        return False
    payload: dict[str, Any] = {"message": message}
    if document_id is not None:
        payload["document_id"] = document_id
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
        )
        return True
    except WebPushException as exc:
        logger.warning("Web push failed: %s", exc)
        return False


async def send_push_to_users(
    session: AsyncSession,
    user_ids: set[int],
    message: str,
    event_type: NotificationEventType,
    *,
    document_id: int | None = None,
) -> None:
    if not VAPID_PRIVATE_KEY or not user_ids:
        return

    from sqlalchemy.future import select

    result = await session.execute(select(User).where(User.id.in_(user_ids)))
    users = result.scalars().all()
    stale_user_ids: list[int] = []

    for user in users:
        if not user.push_subscription or not user_wants_push(user, event_type):
            continue
        if not send_web_push(user.push_subscription, message, document_id=document_id):
            stale_user_ids.append(user.id)

    for user_id in stale_user_ids:
        stale = await session.get(User, user_id)
        if stale:
            stale.push_subscription = None
