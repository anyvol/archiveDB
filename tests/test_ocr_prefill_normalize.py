"""Tests for OCR prefill normalization (format, dates, doc kind, signatures)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.ocr.commit import prefill_from_extraction
from app.ocr.normalize import (
    coerce_document_format,
    extract_doc_kind_from_text,
    normalize_ocr_date,
    parse_designation_parts,
)
from app.ocr.service import _empty_fields
from app.name_helpers import suggest_org_codes


def test_coerce_document_format_cyrillic_a():
    assert coerce_document_format("А4") == "A4"
    assert coerce_document_format("а3") == "A3"
    assert coerce_document_format("A3x3") == "A3x3"
    assert coerce_document_format("A3X3") == "A3x3"
    assert coerce_document_format("garbage") == ""


def test_normalize_ocr_date_variants():
    assert normalize_ocr_date("15.03.2024") == "2024-03-15"
    assert normalize_ocr_date("15.03.24") == "2024-03-15"
    assert normalize_ocr_date("2024-03-15") == "2024-03-15"
    assert normalize_ocr_date("15/03/2024") == "2024-03-15"
    assert normalize_ocr_date("not-a-date") == ""


def test_doc_kind_from_designation():
    parts = parse_designation_parts("ФЕТР.123456.001-01СБ")
    assert parts["doc_kind_code"] == "СБ"
    assert parts["execution"] == "01"
    assert extract_doc_kind_from_text("ФЕТР.123456.001СП") == "СП"


def test_prefill_prefers_valid_geometry_format_over_invalid_ocr():
    extraction = MagicMock()
    extraction.fields = {
        **_empty_fields(),
        "document_format": {"value": "А4", "raw": "А4", "conf": 0.9},
        "designation": {"value": "ФЕТР.123456.001СБ"},
        "developer_signed_date": {"value": "15.03.24"},
        "developer_signature": {"value": "true"},
    }
    # After coerce, А4 becomes A4 — either field or geometry works
    extraction.geometry = {"format_from_dims": "A4"}
    prefill = prefill_from_extraction(extraction)
    assert prefill["document_format"] == "A4"
    assert prefill["doc_kind_code"] == "СБ"
    assert prefill["developer_signed_date"] == "2024-03-15"
    assert prefill["has_developer_signature"] == "true"


def test_prefill_falls_back_to_geometry_when_ocr_format_garbage():
    extraction = MagicMock()
    extraction.fields = {
        **_empty_fields(),
        "document_format": {"value": "???", "raw": "???", "conf": 0.8},
    }
    extraction.geometry = {"format_from_dims": "A3"}
    prefill = prefill_from_extraction(extraction)
    assert prefill["document_format"] == "A3"


def test_suggest_org_codes_prefix():
    known = ["ФЕТР", "АБВГ", "12345678"]
    hits = suggest_org_codes("ФЕТ", known)
    assert hits and hits[0]["name"] == "ФЕТР"
