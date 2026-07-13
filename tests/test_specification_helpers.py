"""Tests for specification designation helpers."""

from app.specification_helpers import strip_assembly_kind_suffix


def test_strip_assembly_kind_suffix():
    assert strip_assembly_kind_suffix("ФЕТР.301524.002СБ") == "ФЕТР.301524.002"
    assert strip_assembly_kind_suffix("ФЕТР.301524.002") == "ФЕТР.301524.002"
