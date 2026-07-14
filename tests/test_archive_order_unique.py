"""Regression for ArchiveOrder joinedload unique() requirement."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import ArchiveOrder


@pytest.mark.asyncio
async def test_get_archive_order_uses_unique_on_collection_eager_load():
    from app.archive_records import get_archive_order

    order = ArchiveOrder(id=7, number="1", name="Test")
    unique_result = MagicMock()
    unique_result.one_or_none.return_value = order
    scalars_result = MagicMock()
    scalars_result.unique.return_value = unique_result
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result

    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    found = await get_archive_order(session, 7)

    assert found is order
    session.execute.assert_awaited_once()
    execute_result.scalars.assert_called_once_with()
    scalars_result.unique.assert_called_once_with()
    unique_result.one_or_none.assert_called_once_with()
    execute_result.scalar_one_or_none.assert_not_called()
