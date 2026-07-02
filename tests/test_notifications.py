"""Tests for notification recipient selection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import BaseDocument, NotificationEventType, User, UserRole
from app.notifications import notify_document_delete, send_document_delete_push


def _scalar_result(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_notify_document_delete_notifies_all_users_except_actor():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_scalar_result([1, 2, 3, 4]))

    doc = BaseDocument(id=10, uploaded_by=2, type="DD")
    doc.design_document = None
    doc.tech_document = None

    actor = User(id=3, login="admin", role=UserRole.admin)

    with patch("app.notifications._create_notifications", new_callable=AsyncMock) as create_notifications:
        result = await notify_document_delete(session, doc, actor, "Removed by mistake")

    create_notifications.assert_awaited_once()
    args, kwargs = create_notifications.await_args
    assert args[1] == {1, 2, 4}
    assert args[4] == NotificationEventType.document_delete
    assert kwargs["send_push"] is False
    assert result == ({1, 2, 4}, "admin удалил(а) документ «#10» с комментарием «Removed by mistake»")


@pytest.mark.asyncio
async def test_send_document_delete_push_delegates_to_push_helper():
    session = AsyncMock()
    recipients = {1, 2}
    message = "Deleted"

    with patch("app.notifications.send_push_to_users", new_callable=AsyncMock) as send_push:
        await send_document_delete_push(session, recipients, message)

    send_push.assert_awaited_once_with(
        session, recipients, message, NotificationEventType.document_delete
    )
