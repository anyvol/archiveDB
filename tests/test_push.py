"""Tests for push notification preferences."""

from unittest.mock import patch

from requests.exceptions import ConnectionError

from app.models import NotificationEventType
from app.push import DEFAULT_PUSH_PREFERENCES, normalize_push_preferences, send_web_push, user_wants_push


class _UserStub:
    push_preferences = None
    push_subscription = {"endpoint": "https://example.com/push"}


def test_normalize_push_preferences_defaults():
    prefs = normalize_push_preferences(None)
    assert prefs == DEFAULT_PUSH_PREFERENCES


def test_user_wants_push_respects_event_toggle():
    user = _UserStub()
    user.push_preferences = {
        "enabled": True,
        "upload": False,
        "status_change": True,
        "document_edit": True,
        "document_register": True,
        "document_delete": True,
    }
    assert not user_wants_push(user, NotificationEventType.upload)
    assert user_wants_push(user, NotificationEventType.status_change)


def test_send_web_push_handles_connection_error():
    subscription = {"endpoint": "https://fcm.googleapis.com/fcm/send/test"}
    with patch("app.push.VAPID_PRIVATE_KEY", "test-key"), patch(
        "app.push.webpush",
        side_effect=ConnectionError("Failed to resolve fcm.googleapis.com"),
    ):
        assert send_web_push(subscription, "hello", document_id=1) is False
