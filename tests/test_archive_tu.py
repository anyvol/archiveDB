"""Tests for archive technical specifications (ТУ)."""

import pytest
from fastapi import HTTPException

from app.archive_records import build_tu_number, parse_tu_number


def test_build_tu_number_valid():
    number = build_tu_number("26.20.13", "2", "95979699", 2024)
    assert number == "26.20.13-002-95979699-2024"


def test_build_tu_number_invalid_okpd2():
    with pytest.raises(HTTPException) as exc:
        build_tu_number("invalid", "002", "95979699", 2024)
    assert exc.value.status_code == 400


def test_parse_tu_number():
    parsed = parse_tu_number("26.20.13-002-95979699-2024")
    assert parsed["okpd2"] == "26.20.13"
    assert parsed["product_index"] == "002"
    assert parsed["okpo"] == "95979699"
    assert parsed["year"] == 2024
