"""Phase 3: OCR dataset export (unit tests, no DB)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import OcrJobStatus
from app.ocr.dataset import _sample_payload, build_dataset_zip, dataset_stats


def _png_bytes() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )


@pytest.mark.asyncio
async def test_dataset_export_zip_contains_manifest_and_images(monkeypatch, tmp_path):
    upload_root = tmp_path
    stamp = upload_root / "ocr" / "stamp.png"
    page = upload_root / "ocr" / "page.png"
    stamp.parent.mkdir(parents=True)
    stamp.write_bytes(_png_bytes())
    page.write_bytes(_png_bytes())

    monkeypatch.setattr("app.ocr.dataset.UPLOAD_DIR", str(upload_root))

    extraction = SimpleNamespace(
        source="training",
        fields={
            "document_format": {
                "value": "A4",
                "raw": "A4",
                "conf": 0.9,
                "bbox_norm": [0.1, 0.1, 0.2, 0.2],
            },
        },
        geometry={
            "stamp_roi": {
                "stamp_roi_norm": [0.55, 0.72, 0.98, 0.98],
                "stamp_roi_source": "annotation",
            },
            "format_from_dims": "A4",
            "dpi": 400,
        },
        stamp_crop_path=str(stamp),
        page_preview_path=str(page),
    )
    annotation = SimpleNamespace(
        id=7,
        labels={
            "document_format": "A4",
            "stamp_roi_norm": [0.55, 0.72, 0.98, 0.98],
            "cells": [{"key": "designation", "bbox_norm": [0.1, 0.2, 0.8, 0.35]}],
        },
        updated_at=datetime.utcnow(),
        exported_at=None,
    )
    job = SimpleNamespace(
        id=42,
        batch_id=1,
        original_filename="sheet.pdf",
        mime="application/pdf",
        status=OcrJobStatus.labeled,
        pipeline_version="stamp-cells-1.1",
        extractions=[extraction],
        annotations=[annotation],
    )
    template = SimpleNamespace(
        document_format="A4",
        labels={"stamp_roi_norm": [0.55, 0.72, 0.98, 0.98]},
        updated_at=datetime.utcnow(),
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    # list_exportable_jobs path uses session.execute twice in build_dataset_zip
    # (jobs via list_exportable_jobs, then templates). Patch list_exportable_jobs.
    async def _fake_list(_session):
        return [job]

    monkeypatch.setattr("app.ocr.dataset.list_exportable_jobs", _fake_list)

    templates_result = MagicMock()
    templates_result.scalars.return_value.all.return_value = [template]
    session.execute = AsyncMock(return_value=templates_result)

    zip_bytes, summary = await build_dataset_zip(session, mark_exported=True)
    assert summary["sample_count"] == 1
    assert summary["format_template_count"] == 1
    assert summary["filename"].endswith(".zip")
    assert annotation.exported_at is not None
    session.commit.assert_awaited()

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = set(zf.namelist())
    assert any(n.endswith("manifest.json") for n in names)
    assert any(n.endswith("format_templates.json") for n in names)
    assert any(n.endswith("samples/job_42/stamp.png") for n in names)
    assert any(n.endswith("samples/job_42/page.png") for n in names)
    assert any(n.endswith("samples/job_42/labels.json") for n in names)

    manifest_name = next(n for n in names if n.endswith("manifest.json"))
    manifest = json.loads(zf.read(manifest_name))
    assert manifest["schema_version"] == "1.0"
    assert manifest["sample_count"] == 1

    labels_name = next(n for n in names if n.endswith("labels.json"))
    labels = json.loads(zf.read(labels_name))
    assert labels["job_id"] == 42
    assert labels["stamp_roi_norm"] == [0.55, 0.72, 0.98, 0.98]
    assert labels["files"]["stamp"] == "stamp.png"
    assert labels["files"]["page"] == "page.png"


@pytest.mark.asyncio
async def test_dataset_stats_counts(monkeypatch):
    job = SimpleNamespace(
        status=OcrJobStatus.labeled,
        annotations=[SimpleNamespace()],
        extractions=[],
    )

    async def _fake_list(_session):
        return [job]

    monkeypatch.setattr("app.ocr.dataset.list_exportable_jobs", _fake_list)
    session = AsyncMock()
    templates_result = MagicMock()
    templates_result.scalars.return_value.all.return_value = [
        SimpleNamespace(document_format="A3", labels={"stamp_roi_norm": [0.1, 0.2, 0.9, 0.9]})
    ]
    session.execute = AsyncMock(return_value=templates_result)
    stats = await dataset_stats(session)
    assert stats["exportable_jobs"] == 1
    assert stats["labeled_jobs"] == 1
    assert stats["annotated_jobs"] == 1
    assert stats["format_templates"][0]["document_format"] == "A3"
    assert stats["format_templates"][0]["has_stamp_roi"] is True


def test_sample_payload_prefers_annotation_roi():
    job = SimpleNamespace(
        id=1,
        batch_id=2,
        original_filename="a.pdf",
        mime="application/pdf",
        status=OcrJobStatus.labeled,
        pipeline_version="stamp-cells-1.1",
    )
    annotation = SimpleNamespace(
        id=9,
        labels={"stamp_roi_norm": [0.1, 0.2, 0.3, 0.4], "document_format": "A4", "cells": []},
    )
    gt = SimpleNamespace(
        source="training",
        fields={},
        geometry={"stamp_roi": {"stamp_roi_norm": [0.9, 0.9, 1.0, 1.0]}, "dpi": 400},
    )
    payload = _sample_payload(job, annotation, gt)
    assert payload["stamp_roi_norm"] == [0.1, 0.2, 0.3, 0.4]
    assert payload["geometry"]["dpi"] == 400


def test_ocr_render_dpi_default_is_400():
    """Higher DPI for clearer stamp text (phase 3)."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "ocr" / "pipeline" / "extract.py").read_text(
        encoding="utf-8"
    )
    assert 'os.getenv("OCR_RENDER_DPI", "400")' in text
    assert 'os.getenv("OCR_PAGE_PREVIEW_MAX_SIDE", "2800")' in text
