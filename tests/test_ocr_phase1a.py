"""Unit tests for OCR phase 1A helpers and client graceful degrade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.document_format import detect_format_from_dimensions
from app.ocr.client import OcrServiceError, call_extract, check_ocr_health
from app.ocr.commit import prefill_from_extraction
from app.ocr.service import _empty_fields, field_value


def test_field_value_reads_value_then_raw():
    fields = {
        "doc_name": {"raw": "raw", "value": "value"},
        "developed_by": {"raw": "Иванов", "value": None},
    }
    assert field_value(fields, "doc_name") == "value"
    assert field_value(fields, "developed_by") == "Иванов"
    assert field_value(fields, "missing") == ""


def test_empty_fields_has_expected_keys():
    fields = _empty_fields()
    assert "designation" in fields
    assert "document_format" in fields
    assert fields["doc_name"]["value"] is None


def test_prefill_parses_designation():
    extraction = MagicMock()
    extraction.fields = {
        "designation": {"value": "ФЕТР.123456.001-01СБ"},
        "doc_name": {"value": "Сборка"},
        "developed_by": {"value": "Иванов"},
        "document_format": {"value": "A3"},
    }
    extraction.geometry = {}
    prefill = prefill_from_extraction(extraction)
    assert prefill["org_code"] == "ФЕТР"
    assert prefill["class_code"] == "123456"
    assert prefill["reg_number"] == "001"
    assert prefill["execution"] == "01"
    assert prefill["doc_kind_code"] == "СБ"
    assert prefill["doc_name"] == "Сборка"
    assert prefill["document_format"] == "A3"


def test_prefill_uses_geometry_format_fallback():
    extraction = MagicMock()
    extraction.fields = _empty_fields()
    extraction.geometry = {"format_from_dims": "A4"}
    prefill = prefill_from_extraction(extraction)
    assert prefill["document_format"] == "A4"


@pytest.mark.asyncio
async def test_check_ocr_health_returns_none_when_down():
    with patch("app.ocr.client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get.side_effect = httpx.ConnectError("refused")
        client_cls.return_value = client
        assert await check_ocr_health() is None


@pytest.mark.asyncio
async def test_call_extract_marks_unavailable_on_connect_error():
    with patch("app.ocr.client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = httpx.ConnectError("refused")
        client_cls.return_value = client
        with pytest.raises(OcrServiceError) as exc_info:
            await call_extract(job_id=1, file_path="/uploads/x.pdf")
        assert exc_info.value.unavailable is True


@pytest.mark.asyncio
async def test_call_extract_success():
    with patch("app.ocr.client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "pipeline_version": "stub-1.0",
            "fields": {},
            "geometry": {"format_from_dims": "A4"},
        }
        client.post.return_value = response
        client_cls.return_value = client
        result = await call_extract(job_id=1, file_path="/uploads/x.pdf")
        assert result["pipeline_version"] == "stub-1.0"


def test_ocr_sidecar_format_detect_a4():
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "ocr" / "format_detect.py"
    spec = importlib.util.spec_from_file_location("ocr_format_detect", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["ocr_format_detect"] = module
    spec.loader.exec_module(module)
    assert module.detect_format_from_dimensions(210, 297) == "A4"
    assert detect_format_from_dimensions(210, 297) == "A4"
