"""Tests for OCR job document reference cleanup on delete."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ocr.service import clear_ocr_job_document_references


@pytest.mark.asyncio
async def test_clear_ocr_job_document_references_updates_jobs():
    session = AsyncMock()
    result = MagicMock()
    session.execute = AsyncMock(return_value=result)

    await clear_ocr_job_document_references(session, 215)

    session.execute.assert_awaited_once()
    stmt = session.execute.await_args.args[0]
    assert "ocr_jobs" in str(stmt).lower()
