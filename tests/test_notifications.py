"""Tests for notification recipient selection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import BaseDocument, User, UserRole
from app.notifications import notify_document_delete


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
        await notify_document_delete(session, doc, actor, "Removed by mistake")

    create_notifications.assert_awaited_once()
    recipients = create_notifications.await_args.args[1]
    assert recipients == {1, 2, 4}
