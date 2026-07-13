"""Tests for OCR batch queue + background processing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import OcrBatchStatus, OcrJobStatus
from app.ocr.service import create_batch_with_files, process_batch_jobs


class _Upload:
    def __init__(self, name: str, data: bytes):
        self.filename = name
        self._data = data

    async def read(self) -> bytes:
        return self._data


@pytest.mark.asyncio
async def test_create_batch_queues_jobs_without_processing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.ocr.service.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("app.ocr.service.MAX_UPLOAD_SIZE_MB", 50)

    session = AsyncMock()
    batch = MagicMock()
    batch.id = 7
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _flush_side_effect():
        if not getattr(batch, "id", None):
            batch.id = 7

    session.flush.side_effect = _flush_side_effect

    process_mock = AsyncMock()
    with patch("app.ocr.service.OcrBatch", return_value=batch), patch(
        "app.ocr.service.process_job", process_mock
    ), patch("app.ocr.service._refresh_batch_status", new_callable=AsyncMock):
        result = await create_batch_with_files(
            session,
            MagicMock(id=1),
            [_Upload("a.pdf", b"%PDF-1.4"), _Upload("b.pdf", b"%PDF-1.4")],
        )

    assert result is batch
    process_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_batch_jobs_runs_queued_jobs():
    job = MagicMock()
    job.id = 11
    job.status = OcrJobStatus.queued

    batch = MagicMock()
    batch.id = 7
    batch.status = OcrBatchStatus.processing

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [job]
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=batch)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session
    session_cm.__aexit__.return_value = None

    process_mock = AsyncMock()
    refresh_mock = AsyncMock()
    with patch("app.ocr.service.async_session", return_value=session_cm), patch(
        "app.ocr.service.process_job", process_mock
    ), patch("app.ocr.service._refresh_batch_status", refresh_mock):
        await process_batch_jobs(7)

    process_mock.assert_awaited_once_with(session, job)
    refresh_mock.assert_awaited_once()
    session.commit.assert_awaited_once()
