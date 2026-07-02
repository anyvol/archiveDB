"""Tests for document format detection."""

from app.document_format import detect_format_from_dimensions, is_valid_document_format


def test_detect_a4_portrait():
    assert detect_format_from_dimensions(210, 297) == "A4"


def test_detect_a4_landscape():
    assert detect_format_from_dimensions(297, 210) == "A4"


def test_detect_a3x3():
    assert detect_format_from_dimensions(1260, 297) == "A3x3"


def test_is_valid_document_format():
    assert is_valid_document_format("A4")
    assert not is_valid_document_format("B4")
